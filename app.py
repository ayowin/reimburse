from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'reimburse.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 初始化扩展
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'admin_login'
login_manager.login_message = '请先登录管理后台'

@login_manager.user_loader
def load_user(user_id):
    """加载用户的回调函数"""
    return User.query.get(int(user_id))

# ==================== 数据库模型 ====================

class User(UserMixin, db.Model):
    """管理员用户表"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), default='admin')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """检查用户是否为管理员"""
        return self.role == 'admin'


class AuthCode(db.Model):
    """全局授权码（只有一个）"""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False)  # 全局唯一的授权码
    is_active = db.Column(db.Boolean, default=True)  # 是否启用
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    updater = db.relationship('User', backref=db.backref('auth_code_updates', lazy='dynamic'))


class Reimbursement(db.Model):
    """报销信息表"""
    id = db.Column(db.Integer, primary_key=True)
    submit_date = db.Column(db.Date, nullable=False)
    department = db.Column(db.String(100), nullable=False)
    applicant = db.Column(db.String(100), nullable=False)
    purpose = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(32), default='pending')  # pending: 待处理，accepted: 已受理，rejected: 未受理
    auth_code_id = db.Column(db.Integer, db.ForeignKey('auth_code.id'))
    submitted_at = db.Column(db.DateTime, default=datetime.now)
    
    attachments = db.relationship('Attachment', backref='reimbursement', lazy='dynamic', cascade='all, delete-orphan')
    audit_logs = db.relationship('AuditLog', backref='reimbursement', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def submit_date_str(self):
        return self.submit_date.strftime('%Y-%m-%d') if self.submit_date else ''


class Attachment(db.Model):
    """附件表"""
    id = db.Column(db.Integer, primary_key=True)
    reimbursement_id = db.Column(db.Integer, db.ForeignKey('reimbursement.id'), nullable=False)
    filename = db.Column(db.String(256), nullable=False)
    stored_filename = db.Column(db.String(256), nullable=False)
    file_type = db.Column(db.String(32))
    file_size = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.now)


class AuditLog(db.Model):
    """审核日志表"""
    id = db.Column(db.Integer, primary_key=True)
    reimbursement_id = db.Column(db.Integer, db.ForeignKey('reimbursement.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(32), nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    user = db.relationship('User', backref=db.backref('audit_logs', lazy='dynamic'))


class OperationLog(db.Model):
    """操作日志表"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    user = db.relationship('User', backref=db.backref('operation_logs', lazy='dynamic'))

# 导入路由
from routes import *

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # 创建默认管理员账号
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', role='admin')
            admin.set_password('123456')
            db.session.add(admin)
            db.session.commit()
            print('已创建默认管理员账号：admin / 123456')
        
        # 创建全局授权码（如果不存在）
        auth_code = AuthCode.query.first()
        if not auth_code:
            import random
            import string
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            auth_code = AuthCode(code=code)
            db.session.add(auth_code)
            db.session.commit()
            print(f'已创建全局授权码：{code}')
    
    app.run(debug=True, host='0.0.0.0', port=5000)
