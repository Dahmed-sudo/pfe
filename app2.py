from flask import Flask, Response, jsonify, render_template, request, redirect, url_for, flash, session, Blueprint
from functools import wraps
import firebase_admin
from firebase_admin import credentials, db as firebase_db, auth
import cv2
from werkzeug.security import generate_password_hash, check_password_hash
import time
import requests
import numpy as np
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, static_folder='static')
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'votre-projet-2025-xyz-aleatoire-987654321')

# Blueprint pour organiser les routes admin
admin_bp = Blueprint('admin', __name__)

# Configuration for file uploads
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Remplacez par l'adresse IP de votre ESP8266
ESP8266_IP = "192.168.155.41"
 
# Initialisation Firebase avec Realtime Database
cred = credentials.Certificate("platforme-81846-firebase-adminsdk-fbsvc-3459812c48.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://platforme-81846-default-rtdb.firebaseio.com/'
})

# Référence à la base de données
db_ref = firebase_db.reference('/')

# Fonction pour le flux vidéo
def generate_frames():
    camera = cv2.VideoCapture(0)
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')

        if not email or '@' not in email:
            flash('Veuillez entrer une adresse e-mail valide.', 'error')
            return render_template('register.html')
        if not password or len(password) < 6:
            flash('Le mot de passe doit contenir au moins 6 caractères.', 'error')
            return render_template('register.html')
        if role not in ['employe', 'admin']:
            flash('Veuillez sélectionner un rôle valide.', 'error')
            return render_template('register.html')

        safe_email = email.replace('.', ',')
        try:
            user_ref = firebase_db.reference('users').child(safe_email)
            if user_ref.get():
                flash('Un compte avec cet e-mail existe déjà.', 'error')
                return render_template('register.html')

            user = auth.create_user(email=email, password=password)
            user_ref.set({
                'email': email,
                'password': generate_password_hash(password),
                'role': role,
                'approved': False
            })

            flash('Inscription réussie ! Veuillez attendre l\'approbation de l\'administrateur.', 'success')
            return redirect(url_for('pending_approval'))
        except auth.EmailAlreadyExistsError:
            flash('Un compte avec cet e-mail existe déjà.', 'error')
            return render_template('register.html')
        except Exception as e:
            flash(f'Erreur lors de l\'inscription : {str(e)}. Veuillez réessayer.', 'error')
            return render_template('register.html')

    return render_template('register.html')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user' not in session or session.get('role') not in ['admin', 'employe']:
        flash('Accès réservé aux employés.', 'error')
        return redirect(url_for('login'))

    safe_email = session['user'].replace('.', ',')
    user_ref = db_ref.child('users').child(safe_email)
    user_data = user_ref.get() or {}

    if request.method == 'POST':
        password = request.form.get('password')
        phone = request.form.get('phone')
        address = request.form.get('address')
        photo = request.files.get('photo')

        updates = {}
        profile_photo = user_data.get('profile_photo')

        if password and len(password) >= 6:
            updates['password'] = generate_password_hash(password)
            try:
                user = auth.get_user_by_email(session['user'])
                auth.update_user(user.uid, password=password)
                flash('Mot de passe mis à jour avec succès.', 'success')
            except Exception as e:
                flash(f'Erreur lors de la mise à jour du mot de passe : {str(e)}.', 'error')
        elif password and len(password) < 6:
            flash('Le mot de passe doit contenir au moins 6 caractères.', 'error')

        if phone:
            updates['phone'] = phone
        if address:
            updates['address'] = address
 
        if photo and allowed_file(photo.filename):
            filename = secure_filename(f"{safe_email}_{photo.filename}")
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            photo.save(photo_path)
            profile_photo = url_for('static', filename=f'uploads/{filename}', _external=False)
            updates['profile_photo'] = profile_photo

        if updates:
            try:
                user_ref.update(updates)
                flash('Profil mis à jour avec succès.', 'success')
            except Exception as e:
                flash(f'Erreur lors de la mise à jour du profil : {str(e)}.', 'error')

        user_data = user_ref.get() or {}
        phone = user_data.get('phone')
        address = user_data.get('address')
        profile_photo = profile_photo or user_data.get('profile_photo')

        return render_template(
            'profile.html',
            user_email=session['user'],
            profile_photo=profile_photo,
            phone=phone,
            address=address
        )

    profile_photo = user_data.get('profile_photo')
    phone = user_data.get('phone') 
    address = user_data.get('address')

    return render_template(
        'profile.html',
        user_email=session['user'],
        profile_photo=profile_photo,
        phone=phone,
        address=address
    )

@app.route('/pending_approval')
def pending_approval():
    return render_template('pending_approval.html')

@app.route('/approve_users', methods=['GET', 'POST'])
def approve_users():
    if 'user' not in session or session.get('role') != 'admin':
        flash('Accès réservé aux administrateurs.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        email = request.form.get('email')
        action = request.form.get('action')
        if not email or not action:
            flash('Requête invalide : email ou action manquant.', 'error')
            return redirect(url_for('approve_users'))

        safe_email = email.replace('.', ',')

        user_ref = db_ref.child('users').child(safe_email)
        user = user_ref.get()

        if not user:
            flash('Utilisateur non trouvé.', 'error')
            return redirect(url_for('approve_users'))

        try:
            if action == 'approve':
                user_ref.update({'approved': True})
                flash(f'Utilisateur {email} approuvé avec succès.', 'success')
            elif action == 'reject':
                user_ref.delete()
                flash(f'Utilisateur {email} rejeté.', 'info')
            elif action == 'remove':
                user_ref.delete()
                flash(f'Employé {email} supprimé.', 'info')
            else:
                flash('Action non valide.', 'error')
        except Exception as e:
            flash(f'Erreur lors de la mise à jour : {str(e)}.', 'error')

        return redirect(url_for('approve_users'))

    users = db_ref.child('users').get() or {}
    pending_users = []
    approved_employees = []

    for safe_email, user_data in users.items():
        user_email = safe_email.replace(',', '.')
        user = {
            'email': user_email,
            'role': user_data.get('role', 'employe'),
            'approved': user_data.get('approved', False)
        }
        if user['approved']:
            approved_employees.append(user)
        else:
            pending_users.append(user)

    return render_template(
        'approve_users.html',
        pending_users=pending_users,
        approved_employees=approved_employees
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user_ref = db_ref.child('users').child(email.replace('.', ','))
        user = user_ref.get()
        
        if user and check_password_hash(user['password'], password):
            if not user.get('approved', False):
                flash("Votre compte n'a pas encore été approuvé par l'administrateur.", 'error')
                return redirect(url_for('login'))
            
            session['user'] = email
            session['role'] = user.get('role', 'employe')
            
            if session['role'] == 'admin':
                return redirect(url_for('admihome'))
            else:
                return redirect(url_for('employee_home'))
        else:
            flash("Email ou mot de passe incorrect.", 'error')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email')
        if not email or '@' not in email:
            flash('Veuillez entrer une adresse e-mail valide.', 'error')
            return render_template('reset_password.html')
        
        safe_email = email.replace('.', ',')
        try:
            user_ref = firebase_db.reference('users').child(safe_email)
            user = user_ref.get()
            
            if not user:
                flash('Aucun compte trouvé avec cet e-mail.', 'error')
                return render_template('reset_password.html')
            
            try:
                auth.get_user_by_email(email)
            except auth.UserNotFoundError:
                flash('Compte non enregistré dans le système d\'authentification.', 'error')
                return render_template('reset_password.html')
            
            link = auth.generate_password_reset_link(email)
            
            sender_email = os.getenv('GMAIL_SENDER_EMAIL', 'industrieindustrie1@gmail.com')
            sender_password = os.getenv('GMAIL_APP_PASSWORD', '12344321PFE')
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = email
            msg['Subject'] = 'Réinitialisation de votre mot de passe'
            body = f"""
            Bonjour,

            Cliquez sur le lien suivant pour réinitialiser votre mot de passe :
            {link}

            Si vous n'avez pas demandé cette réinitialisation, ignorez cet e-mail.

            Cordialement,
            Votre Application
            """
            msg.attach(MIMEText(body, 'plain'))
            
            try:
                with smtplib.SMTP('smtp.gmail.com', 587) as server:
                    server.starttls()
                    server.login(sender_email, sender_password)
                    server.send_message(msg)
                flash(f'Un lien de réinitialisation a été envoyé à {email}.', 'success')
                return redirect(url_for('login'))
            except smtplib.SMTPAuthenticationError as e:
                print(f"SMTP Authentication Error: {str(e)}")
                flash('Erreur d\'authentification SMTP. Vérifiez les identifiants Gmail ou contactez l\'administrateur.', 'error')
                return render_template('reset_password.html')
            except smtplib.SMTPException as e:
                print(f"SMTP Error: {str(e)}")
                flash(f'Erreur lors de l\'envoi de l\'e-mail : {str(e)}. Veuillez réessayer.', 'error')
                return render_template('reset_password.html')
            
        except Exception as e:
            print(f"General Error: {str(e)}")
            flash(f'Erreur : {str(e)}. Veuillez réessayer ou contacter le support.', 'error')
            return render_template('reset_password.html')
    
    return render_template('reset_password.html')

@app.route('/admihome')
def admihome():
    if 'user' in session and session.get('role') == 'admin':
        sensors_data = db_ref.child('sensors').get() or {}
        current_data = {
            'temperature': sensors_data.get('dht11', {}).get('temperature', 0),
            'humidity': sensors_data.get('dht11', {}).get('humidity', 0),
            'gas': sensors_data.get('gas', {}).get('value', 0),
            'flame': sensors_data.get('flame', {}).get('detection', False),
            'vibration': sensors_data.get('vibration', {}).get('detection', False)
        }
        sensor_history = db_ref.child('sensor_data').order_by_key().limit_to_last(10).get()
        return render_template('admihome.html', 
                             user_email=session['user'],
                             sensor_data=current_data,
                             sensor_history=sensor_history)
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('role', None)
    flash('Vous êtes déconnecté.', 'success')
    return redirect(url_for('home'))

@app.route("/controle de machine")
def controledemachine():
    if 'user' in session:
        sensors_data = db_ref.child('sensors').get() or {}
        current_data = {
            'temperature': sensors_data.get('dht11', {}).get('temperature', 0),
            'humidity': sensors_data.get('dht11', {}).get('humidity', 0),
            'gas': sensors_data.get('gas', {}).get('value', 0),
            'flame': sensors_data.get('flame', {}).get('detection', False),
            'vibration': sensors_data.get('vibration', {}).get('detection', False)
        }
        latest_data = db_ref.child('sensor_data').order_by_key().limit_to_last(1).get()
        chart_data = db_ref.child('sensor_data').order_by_key().limit_to_last(50).get()
        return render_template("controle de machine.html",
                             sensor_data=current_data,
                             latest_data=latest_data,
                             chart_data=chart_data)
    return redirect(url_for('login'))

@app.route("/data1")
def data1():
    if 'user' not in session:
        return redirect(url_for('login'))
    sensors_data = db_ref.child('sensors').get() or {}
    bottle_counts = db_ref.child('bottle_counts').get() or {}
    total_bottle_count = bottle_counts.get('totalBottleCount', 0)
    remaining_bottle_count = bottle_counts.get('remainingBottleCount', 0)
    no_cap_bottle_count = bottle_counts.get('noCapBottleCount', 0)
    return render_template('data1.html',  
                         total_bottle_count=total_bottle_count,
                         remaining_bottle_count=remaining_bottle_count,
                         no_cap_bottle_count=no_cap_bottle_count)

@app.route('/get_data')
def get_data():
    sensors_data = db_ref.child('sensors').get() or {}
    bottle_counts = db_ref.child('bottle_counts').get() or {}
    cap_distance = sensors_data.get('cap_sensor', {}).get('distance', 100)
    bottle_distance = sensors_data.get('bottle_sensor', {}).get('distance', 100)

    if cap_distance < 10 and bottle_distance > 50:
        try:
            response = requests.get(f"http://{ESP8266_IP}/servo?angle=180&duration=500")
            if response.status_code == 200:
                db_ref.child('sensor_data').push({
                    'event': 'cap_without_bottle',
                    'action': 'servo_rotated_180',
                    'timestamp': time.time()
                })
        except requests.exceptions.RequestException as e:
            print(f"Error sending servo command: {e}")

    return jsonify({
        'temperature': sensors_data.get('dht11', {}).get('temperature', 0),
        'humidity': sensors_data.get('dht11', {}).get('humidity', 0),
        'gas_value': sensors_data.get('gas', {}).get('value', 0),
        'flame': sensors_data.get('flame', {}).get('value', 0),
        'vibration': sensors_data.get('vibration', {}).get('value', 0),
        'cap_distance': cap_distance,
        'bottle_distance': bottle_distance,
        'total_bottle_count': bottle_counts.get('totalBottleCount', 0),
        'remaining_bottle_count': bottle_counts.get('remainingBottleCount', 0),
        'no_cap_bottle_count': bottle_counts.get('noCapBottleCount', 0),
        'timestamp': time.time()
    })

@app.route('/update_bottle_count', methods=['POST'])
def update_bottle_count():
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Utilisateur non connecté'}), 401

    data = request.get_json()
    total_bottle_count = data.get('totalBottleCount')
    no_cap_bottle_count = data.get('noCapBottleCount')
    remaining_bottle_count = data.get('remainingBottleCount')

    if total_bottle_count is None or no_cap_bottle_count is None or remaining_bottle_count is None:
        return jsonify({'status': 'error', 'message': 'Données manquantes'}), 400

    try:
        db_ref.child('bottle_counts').set({
            'totalBottleCount': total_bottle_count,
            'noCapBottleCount': no_cap_bottle_count,
            'remainingBottleCount': remaining_bottle_count,
            'timestamp': time.time()
        })
        return jsonify({'status': 'success', 'message': 'Comptage des bouteilles mis à jour'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route("/dashbord")
def dashbord():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    sensors_data = db_ref.child('sensors').get() or {}
    bottle_counts = db_ref.child('bottle_counts').get() or {}
    current_data = {
        'temperature': sensors_data.get('dht11', {}).get('temperature', 0),
        'humidity': sensors_data.get('dht11', {}).get('humidity', 0),
        'gas': sensors_data.get('gas', {}).get('value', 0),
        'flame': sensors_data.get('flame', {}).get('value', 0),
        'vibration': sensors_data.get('vibration', {}).get('value', 0),
        'production_efficiency': bottle_counts.get('totalBottleCount', 0)
    }
    chart_data = db_ref.child('sensor_data').order_by_key().limit_to_last(50).get()
    return render_template("dashbord.html", 
                         sensor_data=current_data,
                         chart_data=chart_data,
                         total_bottle_count=bottle_counts.get('totalBottleCount', 0),
                         remaining_bottle_count=bottle_counts.get('remainingBottleCount', 0),
                         no_cap_bottle_count=bottle_counts.get('noCapBottleCount', 0))

@app.route('/set_production_efficiency', methods=['POST'])
def set_production_efficiency():
    data = request.get_json()
    production_efficiency = data.get('production_efficiency')
    return jsonify({'status': 'success', 'production_efficiency': production_efficiency})

@app.route('/employee_home')
def employee_home():
    if 'user' in session and session.get('role') == 'employe':
        return render_template('employee_home.html', user_email=session['user'])
    return redirect(url_for('login'))

@app.route('/manage_sensors', methods=['GET', 'POST'])
def manage_sensors():
    if 'user' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        sensor_name = request.form.get('sensor_name')
        
        if not sensor_name:
            flash("Le nom du capteur est requis.", 'error')
            return redirect(url_for('manage_sensors'))
        
        sensor_ref = db_ref.child('sensors').child(sensor_name)
        
        if action == 'add':
            if sensor_ref.get():
                flash(f"Le capteur {sensor_name} existe déjà.", 'error')
                return redirect(url_for('manage_sensors'))
            
            field_names = request.form.getlist('field_name[]')
            field_values = request.form.getlist('field_value[]')
            sensor_data = {}
            for name, value in zip(field_names, field_values):
                if name and value:
                    try:
                        sensor_data[name] = float(value) if value.replace('.', '', 1).isdigit() else value
                    except ValueError:
                        sensor_data[name] = value
            
            if not sensor_data:
                flash("Au moins un champ valide est requis.", 'error')
                return redirect(url_for('manage_sensors'))
            
            sensor_ref.set(sensor_data)
            flash(f"Capteur {sensor_name} ajouté avec succès!", 'success')
        
        elif action == 'update':
            if not sensor_ref.get():
                flash(f"Le capteur {sensor_name} n'existe pas.", 'error')
                return redirect(url_for('manage_sensors'))
            
            field_names = request.form.getlist('field_name[]')
            field_values = request.form.getlist('field_value[]')
            sensor_data = {}
            for name, value in zip(field_names, field_values):
                if name and value:
                    try:
                        sensor_data[name] = float(value) if value.replace('.', '', 1).isdigit() else value
                    except ValueError:
                        sensor_data[name] = value
            
            if not sensor_data:
                flash("Au moins un champ valide est requis.", 'error')
                return redirect(url_for('manage_sensors'))
            
            sensor_ref.set(sensor_data)
            flash(f"Capteur {sensor_name} mis à jour avec succès!", 'success')
        
        return redirect(url_for('manage_sensors'))
    
    sensors = db_ref.child('sensors').get() or {}
    normalized_sensors = {}
    for name, data in sensors.items():
        if not isinstance(data, dict):
            normalized_sensors[name] = {"value": data}
        else:
            normalized_sensors[name] = data
    
    return render_template('manage_sensors.html', sensors=normalized_sensors)

@app.route("/data")
def data():
    sensors_data = db_ref.child('sensors').get() or {}
    return jsonify({
        'lm35_temperature': sensors_data.get('lm35', {}).get('temperature', 0),
        'temperature': sensors_data.get('dht11', {}).get('temperature', 0),
        'humidity': sensors_data.get('dht11', {}).get('humidity', 0),
        'gas': sensors_data.get('gas', {}).get('value', 0),
        'flame': sensors_data.get('flame', {}).get('value', 0),
        'vibration': sensors_data.get('vibration', {}).get('value', 0)
    })

@app.route("/control", methods=["POST"])
def control():
    action = request.form.get('action')
    try:
        if action == 'on':
            response = requests.get(f"http://{ESP8266_IP}/on")
        elif action == 'off':
            response = requests.get(f"http://{ESP8266_IP}/off")
        elif action == 'status':
            response = requests.get(f"http://{ESP8266_IP}/status")
        else:
            return jsonify({"status": "error", "message": "Action non valide"})
        
        return response.json()
    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)