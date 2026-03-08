from flask import render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from app import app, db, User, AuthCode, Reimbursement, Attachment, AuditLog, OperationLog
from datetime import datetime, timedelta
import os
import uuid

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_type(filename):
    if '.' not in filename:
        return 'other'
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in ['png', 'jpg', 'jpeg']:
        return 'image'
    elif ext == 'pdf':
        return 'pdf'
    return 'other'

# ==================== 移动端前端页面 ====================

@app.route('/')
def index():
    """移动端首页 - 授权码输入"""
    return render_template('mobile/index.html')

@app.route('/submit', methods=['GET', 'POST'])
def submit_reimbursement():
    """报销信息填报页"""
    # 检查是否有授权码
    auth_code = session.get('auth_code')
    if not auth_code:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            submit_date = datetime.strptime(request.form['submit_date'], '%Y-%m-%d').date()
            department = request.form['department']
            applicant = request.form['applicant']
            purpose = request.form['purpose']
            amount = float(request.form['amount'])
            
            # 创建报销记录
            reimbursement = Reimbursement(
                submit_date=submit_date,
                department=department,
                applicant=applicant,
                purpose=purpose,
                amount=amount,
                auth_code_id=auth_code['id']
            )
            db.session.add(reimbursement)
            db.session.flush()  # 获取 ID
            
            # 处理附件上传
            files = request.files.getlist('attachments')
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    # 获取文件扩展名
                    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                    # 使用 UUID 作为存储文件名，保留扩展名
                    stored_filename = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
                    file.save(file_path)
                    
                    attachment = Attachment(
                        reimbursement_id=reimbursement.id,
                        filename=file.filename,  # 保存原始文件名（含中文）
                        stored_filename=stored_filename,
                        file_type=get_file_type(file.filename),
                        file_size=os.path.getsize(file_path)
                    )
                    db.session.add(attachment)
            
            # 更新授权码使用次数（全局授权码不限制使用次数）
            
            db.session.commit()
            
            # 不清除 session 中的授权码，以便继续填报
            # session.pop('auth_code', None)
            
            return jsonify({'success': True, 'message': '报销信息提交成功！'})
            
        except Exception as e:
            db.session.rollback()
            flash(f'提交失败：{str(e)}', 'error')
    
    return render_template('mobile/submit.html', auth_code=auth_code, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/verify_code', methods=['POST'])
def verify_code():
    """验证授权码"""
    code = request.form.get('code')
    if not code:
        return jsonify({'success': False, 'message': '请输入授权码'})
    
    auth_code = AuthCode.query.first()  # 获取全局唯一的授权码
    if not auth_code:
        return jsonify({'success': False, 'message': '系统未配置授权码，请联系管理员'})
    
    if not auth_code.is_active:
        return jsonify({'success': False, 'message': '授权码已停用'})
    
    if auth_code.code != code:
        return jsonify({'success': False, 'message': '授权码无效'})
    
    # 存储授权码到 session
    session['auth_code'] = {
        'id': auth_code.id,
        'code': auth_code.code
    }
    
    return jsonify({'success': True, 'message': '验证通过', 'redirect': url_for('submit_reimbursement')})

# ==================== PC 端管理后台 ====================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """管理员登录"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)

            # 记录登录日志
            log = OperationLog(
                user_id=user.id,
                action='登录',
                details='用户登录系统',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()

            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('admin_dashboard'))
        
        flash('用户名或密码错误', 'error')
    
    return render_template('admin/login.html')

@app.route('/admin/logout')
@login_required
def admin_logout():
    """管理员登出"""
    logout_user()
    return redirect(url_for('admin_login'))

@app.route('/admin')
@login_required
def admin_dashboard():
    """管理后台首页 - 数据统计"""
    # 统计数据
    total_count = Reimbursement.query.count()
    pending_count = Reimbursement.query.filter_by(status='pending').count()
    accepted_count = Reimbursement.query.filter_by(status='accepted').count()
    rejected_count = Reimbursement.query.filter_by(status='rejected').count()
    
    # 部门统计
    departments = db.session.query(
        Reimbursement.department,
        db.func.count(Reimbursement.id),
        db.func.sum(Reimbursement.amount)
    ).group_by(Reimbursement.department).all()
    
    # 最近提交
    recent_submissions = Reimbursement.query.order_by(Reimbursement.submitted_at.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html', 
                         total_count=total_count,
                         pending_count=pending_count,
                         accepted_count=accepted_count,
                         rejected_count=rejected_count,
                         departments=departments,
                         recent_submissions=recent_submissions)

@app.route('/admin/reimbursements')
@login_required
def admin_reimbursements():
    """报销信息管理页"""
    # 搜索条件
    status = request.args.get('status')
    department = request.args.get('department')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    keyword = request.args.get('keyword')
    
    query = Reimbursement.query
    
    if status:
        query = query.filter_by(status=status)
    if department:
        query = query.filter(Reimbursement.department.like(f'%{department}%'))
    if start_date:
        query = query.filter(Reimbursement.submit_date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(Reimbursement.submit_date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    if keyword:
        query = query.filter(
            (Reimbursement.applicant.like(f'%{keyword}%')) |
            (Reimbursement.purpose.like(f'%{keyword}%'))
        )
    
    # 分页参数
    page = request.args.get('page', 1, type=int)
    per_page = 20  # 每页显示20条记录

    # 使用分页
    pagination = query.order_by(Reimbursement.submitted_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    reimbursements = pagination.items
    
    # 所有部门用于筛选
    all_departments = db.session.query(Reimbursement.department).distinct().all()
    
    return render_template('admin/reimbursements.html', 
                         reimbursements=reimbursements,
                         all_departments=all_departments,
                         current_status=status,
                         current_department=department,
                         current_start_date=start_date,
                         current_end_date=end_date,
                         current_keyword=keyword,
                         pagination=pagination)

@app.route('/admin/reimbursement/<int:id>')
@login_required
def admin_reimbursement_detail(id):
    """报销详情"""
    reimbursement = Reimbursement.query.get_or_404(id)
    audit_logs = AuditLog.query.filter_by(reimbursement_id=id).order_by(AuditLog.created_at.desc()).all()
    return render_template('admin/reimbursement_detail.html', 
                         reimbursement=reimbursement,
                         audit_logs=audit_logs)

@app.route('/admin/reimbursement/<int:id>/audit', methods=['POST'])
@login_required
def admin_audit_reimbursement(id):
    """审核报销"""
    reimbursement = Reimbursement.query.get_or_404(id)
    action = request.form.get('action')  # accept or reject
    comment = request.form.get('comment')
    
    if action == 'accept':
        reimbursement.status = 'accepted'
    elif action == 'reject':
        reimbursement.status = 'rejected'
    else:
        flash('无效的审核操作', 'error')
        return redirect(url_for('admin_reimbursement_detail', id=id))
    
    # 记录审核日志
    audit_log = AuditLog(
        reimbursement_id=reimbursement.id,
        user_id=current_user.id,
        action=action,
        comment=comment
    )
    db.session.add(audit_log)
    db.session.commit()
    
    # 记录操作日志
    action_text = '通过' if action == 'accept' else '拒绝'
    log = OperationLog(
        user_id=current_user.id,
        action='审核报销',
        details=f'{action_text}了报销申请（ID: {reimbursement.id}，金额: {reimbursement.amount}元）',
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()

    flash('审核完成', 'success')
    return redirect(url_for('admin_reimbursement_detail', id=id))

@app.route('/admin/authcodes')
@login_required
def admin_auth_codes():
    """授权码管理（全局唯一）"""
    # 只有管理员可以访问授权码管理页面
    if not current_user.is_admin():
        flash('您没有权限访问此页面', 'error')
        return redirect(url_for('admin_dashboard'))

    auth_code = AuthCode.query.first()
    return render_template('admin/auth_codes.html', auth_code=auth_code)

@app.route('/admin/authcode/update', methods=['POST'])
@login_required
def admin_update_auth_code():
    """更新授权码"""
    # 只有管理员可以更新授权码
    if not current_user.is_admin():
        flash('您没有权限执行此操作', 'error')
        return redirect(url_for('admin_dashboard'))

    auth_code = AuthCode.query.first()
    
    if not auth_code:
        # 创建第一个授权码
        import random
        import string
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        auth_code = AuthCode(code=code)
        db.session.add(auth_code)
    else:
        # 更新现有授权码
        action = request.form.get('action')
        if action == 'regenerate':
            import random
            import string
            new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            auth_code.code = new_code
        elif action == 'toggle':
            auth_code.is_active = not auth_code.is_active
        
        auth_code.updated_by = current_user.id
    
    db.session.commit()
    
    flash('授权码已更新', 'success')
    return redirect(url_for('admin_auth_codes'))

@app.route('/admin/users')
@login_required
def admin_users():
    """用户管理"""
    # 只有管理员可以访问用户管理页面
    if not current_user.is_admin():
        flash('您没有权限访问此页面', 'error')
        return redirect(url_for('admin_dashboard'))

    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/create', methods=['POST'])
@login_required
def admin_create_user():
    """新建用户"""
    # 只有管理员可以创建用户
    if not current_user.is_admin():
        flash('您没有权限执行此操作', 'error')
        return redirect(url_for('admin_dashboard'))

    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'admin')
    
    if User.query.filter_by(username=username).first():
        flash('用户名已存在', 'error')
        return redirect(url_for('admin_users'))
    
    user = User(username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    
    flash('用户创建成功', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:id>/delete', methods=['POST'])
@login_required
def admin_delete_user(id):
    """删除用户"""
    # 只有管理员可以删除用户
    if not current_user.is_admin():
        flash('您没有权限执行此操作', 'error')
        return redirect(url_for('admin_dashboard'))

    user = User.query.get_or_404(id)
    # 不允许删除自己
    if user.id == current_user.id:
        flash('不能删除自己的账号', 'error')
        return redirect(url_for('admin_users'))

    db.session.delete(user)
    db.session.commit()

    flash('用户已删除', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:id>/password', methods=['POST'])
@login_required
def admin_change_user_password(id):
    """修改用户密码"""
    # 只有管理员可以修改用户密码
    if not current_user.is_admin():
        flash('您没有权限执行此操作', 'error')
        return redirect(url_for('admin_dashboard'))

    user = User.query.get_or_404(id)
    new_password = request.form.get('password')

    if not new_password or len(new_password) < 6:
        flash('密码长度不能少于6位', 'error')
        return redirect(url_for('admin_users'))

    user.set_password(new_password)
    db.session.commit()

    flash('密码修改成功', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/logs')
@login_required
def admin_logs():
    """操作日志"""
    logs = OperationLog.query.order_by(OperationLog.created_at.desc()).limit(100).all()
    return render_template('admin/logs.html', logs=logs)

@app.route('/upload/<filename>')
@login_required
def uploaded_file(filename):
    """提供附件访问（预览或下载）"""
    from flask import send_file, request
    attachment = Attachment.query.filter_by(stored_filename=filename).first()
    
    if not attachment:
        return '文件不存在', 404
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        return '文件未找到', 404
    
    # 如果是预览模式，设置 Content-Disposition 为 inline
    if request.args.get('preview'):
        return send_file(file_path, as_attachment=False)
    else:
        # 否则作为附件下载
        return send_file(file_path, as_attachment=True, download_name=attachment.filename)
