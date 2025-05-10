from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from pythonosc import udp_client

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///osc_control.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Модель кнопки
class Button(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(20), default='btn-primary')
    order = db.Column(db.Integer, default=0)
    commands = db.relationship('Command', backref='button', lazy=True, cascade='all, delete-orphan')

# Модель команды
class Command(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    button_id = db.Column(db.Integer, db.ForeignKey('button.id'), nullable=False)
    osc_address = db.Column(db.String(200), nullable=False)
    osc_type = db.Column(db.String(16))
    osc_arguments = db.Column(db.String(500))
    osc_ip = db.Column(db.String(50), default='127.0.0.1')
    osc_port = db.Column(db.Integer, default=9000)
    order = db.Column(db.Integer, default=0)

# Создаем таблицы
with app.app_context():
    db.create_all()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.args.get('admin') != 'secret':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    buttons = Button.query.order_by(Button.order).all()
    return render_template('index.html', buttons=buttons)

@app.route('/send_button/<int:button_id>', methods=['POST'])
def send_button(button_id):
    button = Button.query.get_or_404(button_id)
    
    try:
        # Группируем команды по IP:port для оптимизации
        commands_by_client = {}
        for cmd in sorted(button.commands, key=lambda x: x.order):
            key = (cmd.osc_ip, cmd.osc_port)
            if key not in commands_by_client:
                commands_by_client[key] = []
            commands_by_client[key].append(cmd)
        
        # Отправляем команды
        for (ip, port), commands in commands_by_client.items():
            client = udp_client.SimpleUDPClient(ip, port)
            for cmd in commands:
                args = cmd.osc_arguments.split() if cmd.osc_arguments else []
                client.send_message(cmd.osc_address, args)
        
        return jsonify({'status': 'success', 'message': f'Команды кнопки "{button.name}" отправлены'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Ошибка: {str(e)}'})

# Админка для управления кнопками
@app.route('/admin/buttons')
# @login_required
def button_admin():
    buttons = Button.query.order_by(Button.order).all()
    return render_template('button_admin.html', buttons=buttons)

@app.route('/admin/buttons/add', methods=['GET', 'POST'])
# @login_required
def add_button():
    if request.method == 'POST':
        button = Button(
            name=request.form['name'],
            color=request.form['color'],
            order=request.form.get('order', 0)
        )
        db.session.add(button)
        db.session.commit()
        flash('Кнопка успешно добавлена', 'success')
        return redirect(url_for('button_admin'))
    
    return render_template('edit_button.html', button=None)

@app.route('/admin/buttons/edit/<int:button_id>', methods=['GET', 'POST'])
# @login_required
def edit_button(button_id):
    button = Button.query.get_or_404(button_id)
    
    if request.method == 'POST':
        button.name = request.form['name']
        button.color = request.form['color']
        button.order = request.form.get('order', 0)
        db.session.commit()
        flash('Кнопка успешно обновлена', 'success')
        return redirect(url_for('button_admin'))
    
    return render_template('edit_button.html', button=button)

@app.route('/admin/buttons/delete/<int:button_id>', methods=['POST'])
# @login_required
def delete_button(button_id):
    button = Button.query.get_or_404(button_id)
    db.session.delete(button)
    db.session.commit()
    flash('Кнопка успешно удалена', 'success')
    return redirect(url_for('button_admin'))

# Админка для управления командами
@app.route('/admin/commands/<int:button_id>')
# @login_required
def command_admin(button_id):
    button = Button.query.get_or_404(button_id)
    commands = Command.query.filter_by(button_id=button_id).order_by(Command.order).all()
    return render_template('command_admin.html', button=button, commands=commands)

@app.route('/admin/commands/add/<int:button_id>', methods=['GET', 'POST'])
# @login_required
def add_command(button_id):
    button = Button.query.get_or_404(button_id)
    
    if request.method == 'POST':
        command = Command(
            button_id=button_id,
            osc_address=request.form['osc_address'],
            osc_arguments=request.form['osc_arguments'],
            osc_ip=request.form['osc_ip'],
            osc_port=request.form['osc_port'],
            order=request.form.get('order', 0)
        )
        db.session.add(command)
        db.session.commit()
        flash('Команда успешно добавлена', 'success')
        return redirect(url_for('command_admin', button_id=button_id))
    
    return render_template('edit_command.html', button=button, command=None)

@app.route('/admin/commands/edit/<int:command_id>', methods=['GET', 'POST'])
# @login_required
def edit_command(command_id):
    command = Command.query.get_or_404(command_id)
    button = command.button
    
    if request.method == 'POST':
        command.osc_address = request.form['osc_address']
        command.osc_arguments = request.form['osc_arguments']
        command.osc_ip = request.form['osc_ip']
        command.osc_port = request.form['osc_port']
        command.order = request.form.get('order', 0)
        db.session.commit()
        flash('Команда успешно обновлена', 'success')
        return redirect(url_for('command_admin', button_id=button.id))
    
    return render_template('edit_command.html', button=button, command=command)

@app.route('/admin/commands/delete/<int:command_id>', methods=['POST'])
# @login_required
def delete_command(command_id):
    command = Command.query.get_or_404(command_id)
    button_id = command.button_id
    db.session.delete(command)
    db.session.commit()
    flash('Команда успешно удалена', 'success')
    return redirect(url_for('command_admin', button_id=button_id))

if __name__ == '__main__':
    app.run(debug=True)