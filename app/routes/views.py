from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, login_user, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from app import db, login_manager
from app.models.database import User, Setting
from app.models.system_manager import SystemManager
from app.hardware.scale import ScaleManager
from app.utils.helpers import change_region_tr, change_operation_tr
from app.models.database import User, Setting, Customer, CustomerTransaction
from app.models.database import TRANSACTION_PRODUCT_IN, TRANSACTION_PRODUCT_OUT, TRANSACTION_SCRAP_IN, TRANSACTION_SCRAP_OUT
from datetime import datetime
# Blueprint oluştur
main_bp = Blueprint('main', __name__)


# Flask-Login için kullanıcı yükleme işlevi
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@main_bp.route('/')
def index():
    """Ana sayfa"""
    return redirect(url_for('main.dashboard'))


@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Giriş sayfası"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('main.dashboard'))
        else:
            flash('Hatalı kullanıcı adı veya şifre!')

    return render_template('login.html')


@main_bp.route('/logout')
@login_required
def logout():
    """Çıkış yap"""
    logout_user()
    return redirect(url_for('main.login'))


@main_bp.route('/select_setting', methods=['GET', 'POST'])
@login_required
def select_setting():
    """Ayar seçim sayfası"""
    if request.method == 'POST':
        setting = request.form.get('setting')
        if setting:
            session['selected_setting'] = setting
            return redirect(url_for('main.dashboard'))

    settings = Setting.query.all()
    return render_template('select_setting.html', settings=settings)


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Kontrol paneli sayfası"""
    # Seçili ayar kontrol
    if 'selected_setting' not in session:
        return redirect(url_for('main.select_setting'))

    selected_setting = session['selected_setting']

    # Ağırlık bilgisini al
    scale_manager = ScaleManager()
    if not scale_manager.scale:
        scale_manager.initialize(simulation_mode=True)
        scale_manager.start_monitoring()

    weight, is_valid = scale_manager.get_current_weight()

    # Bölge durumlarını al
    status = SystemManager.get_status(selected_setting)

    # Biraz format düzenlemesi
    formatted_status = []
    for region, setting_data in status.items():
        region_tr = change_region_tr(region)
        for setting, gram in setting_data.items():
            formatted_status.append({
                'region': region_tr,
                'region_en': region,
                'setting': setting,
                'gram': f"{gram:.2f}"
            })

    # Son işlemleri al
    logs = SystemManager.get_logs(10)  # Son 10 işlem

    return render_template(
        'dashboard.html',
        status=formatted_status,
        logs=logs,
        weight=weight,
        weight_valid=is_valid,
        selected_setting=selected_setting,
        change_region_tr=change_region_tr,  # Bu satırı ekleyin
        change_operation_tr=change_operation_tr  # Bu satırı ekleyin
    )


@main_bp.route('/operations', methods=['GET', 'POST'])
@login_required
def operations():
    """Manuel işlemler sayfası"""
    if 'selected_setting' not in session:
        return redirect(url_for('main.select_setting'))

    selected_setting = session['selected_setting']

    # Ağırlık bilgisini al
    scale_manager = ScaleManager()
    if not scale_manager.scale:
        scale_manager.initialize(simulation_mode=True)
        scale_manager.start_monitoring()

    weight, is_valid = scale_manager.get_current_weight()

    if request.method == 'POST':
        operation_type = request.form.get('operation_type')
        region = request.form.get('region')
        gram = request.form.get('gram', type=float)

        if not gram:
            flash('Geçerli bir gram değeri giriniz!', 'danger')
        else:
            try:
                if operation_type == 'add':
                    if region == 'safe':
                        result = SystemManager.add_item_safe(selected_setting, gram)
                    else:
                        result = SystemManager.add_item(region, selected_setting, gram)
                elif operation_type == 'subtract':
                    if region == 'safe':
                        result = SystemManager.remove_item_safe(selected_setting, gram)
                    else:
                        result = SystemManager.remove_item(region, selected_setting, gram)

                if result:
                    flash('İşlem başarıyla tamamlandı!', 'success')
                else:
                    flash('İşlem gerçekleştirilemedi!', 'danger')

            except Exception as e:
                flash(f'Hata oluştu: {str(e)}', 'danger')

        return redirect(url_for('main.operations'))

    # Bölgeleri al
    regions = ['safe', 'table', 'polish', 'melting', 'saw', 'acid']
    formatted_regions = [{'name': region, 'name_tr': change_region_tr(region)} for region in regions]

    return render_template(
        'operations.html',
        regions=formatted_regions,
        weight=weight,
        weight_valid=is_valid,
        selected_setting=selected_setting
    )


@main_bp.route('/history')
@login_required
def history():
    """İşlem geçmişi sayfası"""
    if 'selected_setting' not in session:
        return redirect(url_for('main.select_setting'))

    logs = SystemManager.get_logs(50)  # Son 50 işlem

    # İşlemleri formatla
    for log in logs:
        log['operation_type_tr'] = change_operation_tr(log['operation_type'])
        log['source_region_tr'] = change_region_tr(log['source_region'])
        log['target_region_tr'] = change_region_tr(log['target_region'])

    return render_template(
        'history.html',
        logs=logs,
        selected_setting=session['selected_setting']
    )


@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Ayarlar sayfası"""
    if not current_user.is_admin:
        flash('Bu sayfaya erişim yetkiniz yok!', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        # Şifre değiştirme
        if 'change_password' in request.form:
            old_password = request.form.get('old_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            if not check_password_hash(current_user.password_hash, old_password):
                flash('Mevcut şifre yanlış!', 'danger')
            elif new_password != confirm_password:
                flash('Yeni şifreler eşleşmiyor!', 'danger')
            else:
                current_user.password_hash = generate_password_hash(new_password)
                db.session.commit()
                flash('Şifre başarıyla değiştirildi!', 'success')

        # Terazi ayarları
        elif 'scale_settings' in request.form:
            port = request.form.get('scale_port')
            simulation = 'simulation_mode' in request.form

            scale_manager = ScaleManager()
            scale_manager.close()
            result = scale_manager.initialize(port=port, simulation_mode=simulation)
            scale_manager.start_monitoring()

            if result:
                flash('Terazi ayarları güncellendi!', 'success')
            else:
                flash('Terazi bağlantısı kurulamadı!', 'danger')

    # Terazi durumunu al
    scale_manager = ScaleManager()
    if not scale_manager.scale:
        scale_manager.initialize(simulation_mode=True)
        scale_manager.start_monitoring()

    scale_connected = scale_manager.scale.is_connected
    scale_simulation = scale_manager.scale.simulation_mode
    scale_port = scale_manager.scale.port

    return render_template(
        'settings.html',
        scale_connected=scale_connected,
        scale_simulation=scale_simulation,
        scale_port=scale_port
    )


@main_bp.route('/change_setting', methods=['POST'])
@login_required
def change_setting():
    """Ayar değiştirme"""
    setting = request.form.get('setting')
    if setting:
        session['selected_setting'] = setting
    return redirect(request.referrer or url_for('main.dashboard'))


@main_bp.route('/tare_scale')
@login_required
def tare_scale():
    """Teraziyi sıfırla"""
    scale_manager = ScaleManager()
    if scale_manager.scale:
        result = scale_manager.tare()
        if result:
            flash('Terazi sıfırlandı!', 'success')
        else:
            flash('Terazi sıfırlanamadı!', 'danger')
    else:
        flash('Terazi bağlantısı yok!', 'danger')

    return redirect(request.referrer or url_for('main.dashboard'))


@main_bp.route('/customers')
@login_required
def customers():
    """Müşteriler sayfası"""
    search = request.args.get('search', '')
    customers_list = SystemManager.get_customers(search)

    return render_template(
        'customers.html',
        customers=customers_list,
        search=search
    )


@main_bp.route('/customers/add', methods=['GET', 'POST'])
@login_required
def add_customer():
    """Müşteri ekleme sayfası"""
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        address = request.form.get('address')

        if not name:
            flash('Müşteri adı gereklidir!', 'danger')
        else:
            try:
                customer = SystemManager.add_customer(name, phone, email, address)
                flash('Müşteri başarıyla eklendi!', 'success')
                return redirect(url_for('main.customer_detail', customer_id=customer.id))
            except Exception as e:
                flash(f'Hata oluştu: {str(e)}', 'danger')

    return render_template('customer_form.html')


@main_bp.route('/customers/<int:customer_id>')
@login_required
def customer_detail(customer_id):
    """Müşteri detay sayfası"""
    customer = SystemManager.get_customer(customer_id)
    if not customer:
        flash('Müşteri bulunamadı!', 'danger')
        return redirect(url_for('main.customers'))

    # Seçili ayar kontrolü
    if 'selected_setting' not in session:
        return redirect(url_for('main.select_setting'))

    selected_setting = session['selected_setting']

    # Müşteri bakiyesi
    balance = SystemManager.get_customer_balance(customer_id)

    # Has altın bakiyesi - sistem hazır değilse boş değer gönderin
    try:
        pure_gold_balance = SystemManager.get_customer_pure_gold_balance(customer_id)
    except (AttributeError, Exception):
        pure_gold_balance = {
            'pure_gold_inputs': 0.0,
            'pure_gold_outputs': 0.0,
            'net_pure_gold': 0.0,
            'labor_pure_gold_inputs': 0.0,
            'labor_pure_gold_outputs': 0.0,
            'net_labor_pure_gold': 0.0,
            'total_net_pure_gold': 0.0
        }

    # Müşteri işlemleri
    transactions = SystemManager.get_customer_transactions(customer_id)

    return render_template(
        'customer_detail.html',
        customer=customer,
        balance=balance,
        pure_gold_balance=pure_gold_balance,
        transactions=transactions,
        selected_setting=selected_setting
    )


@main_bp.route('/customers/<int:customer_id>/add_transaction', methods=['GET', 'POST'])
@login_required
def add_customer_transaction(customer_id):
    """Müşteri işlemi ekleme sayfası"""
    customer = SystemManager.get_customer(customer_id)
    if not customer:
        flash('Müşteri bulunamadı!', 'danger')
        return redirect(url_for('main.customers'))

    # Seçili ayar kontrolü
    if 'selected_setting' not in session:
        return redirect(url_for('main.select_setting'))

    selected_setting = session['selected_setting']

    # Ayara göre milyem değerini al
    setting = Setting.query.filter_by(name=selected_setting).first()
    setting_purity = 916  # Varsayılan değer (22 ayar)

    # Setting modeli purity_per_thousand alanına sahipse kullan
    if hasattr(setting, 'purity_per_thousand'):
        setting_purity = setting.purity_per_thousand

    # Ağırlık bilgisini al
    scale_manager = ScaleManager()
    if not scale_manager.scale:
        scale_manager.initialize(simulation_mode=True)
        scale_manager.start_monitoring()

    weight, is_valid = scale_manager.get_current_weight()

    if request.method == 'POST':
        transaction_type = request.form.get('transaction_type')
        product_description = request.form.get('product_description')
        gram = request.form.get('gram', type=float)
        purity_per_thousand = request.form.get('purity_per_thousand', type=int, default=setting_purity)
        labor_percentage = request.form.get('labor_percentage', type=float, default=0)
        notes = request.form.get('notes')

        # TL alanları kaldırıldı - varsayılan değerler atanıyor
        unit_price = None
        labor_cost = 0
        total_amount = 0

        if not transaction_type or not gram:
            flash('İşlem tipi ve gram değeri gereklidir!', 'danger')
        else:
            try:
                # Has değerleri için model uygunsa has hesaplamalarını kullan
                if hasattr(CustomerTransaction, 'pure_gold_weight'):
                    transaction = SystemManager.add_customer_transaction(
                        customer_id=customer_id,
                        transaction_type=transaction_type,
                        setting_name=selected_setting,
                        gram=gram,
                        product_description=product_description,
                        unit_price=unit_price,
                        labor_cost=labor_cost,
                        purity_per_thousand=purity_per_thousand,
                        labor_percentage=labor_percentage,
                        notes=notes
                    )
                else:
                    # Eski methodu kullan
                    customer = Customer.query.get(customer_id)
                    setting_id = SystemManager.get_setting_id(selected_setting)

                    if not customer or not setting_id:
                        flash('Müşteri veya ayar bulunamadı!', 'danger')
                        return redirect(url_for('main.customers'))

                    transaction = CustomerTransaction(
                        customer_id=customer_id,
                        transaction_type=transaction_type,
                        setting_id=setting_id,
                        gram=float(gram),
                        product_description=product_description,
                        unit_price=unit_price,
                        labor_cost=labor_cost,
                        total_amount=total_amount,
                        notes=notes
                    )

                    db.session.add(transaction)

                    # Kasadan ürün çıkışı veya hurda çıkışı için kasa stokunu güncelle
                    if transaction_type in [TRANSACTION_PRODUCT_OUT, TRANSACTION_SCRAP_OUT]:
                        SystemManager.remove_item_safe(selected_setting, gram)

                    # Ürün girişi veya hurda girişi için kasa stokunu güncelle
                    elif transaction_type in [TRANSACTION_PRODUCT_IN, TRANSACTION_SCRAP_IN]:
                        SystemManager.add_item_safe(selected_setting, gram)

                    db.session.commit()

                flash('İşlem başarıyla eklendi!', 'success')
                return redirect(url_for('main.customer_detail', customer_id=customer_id))

            except Exception as e:
                flash(f'Hata oluştu: {str(e)}', 'danger')
                print(f"İşlem eklenirken hata: {str(e)}")

    # İşlem türleri
    transaction_types = [
        {'value': 'PRODUCT_IN', 'label': 'Ürün Giriş (Müşteriden Al)'},
        {'value': 'PRODUCT_OUT', 'label': 'Ürün Çıkış (Müşteriye Ver)'},
        {'value': 'SCRAP_IN', 'label': 'Hurda Giriş (Müşteriden Al)'},
        {'value': 'SCRAP_OUT', 'label': 'Hurda Çıkış (Müşteriye Ver)'}
    ]

    return render_template(
        'customer_transaction_form.html',
        customer=customer,
        transaction_types=transaction_types,
        selected_setting=selected_setting,
        setting_purity=setting_purity,
        weight=weight,
        weight_valid=is_valid
    )


@main_bp.route('/transactions/<int:transaction_id>')
@login_required
def transaction_detail(transaction_id):
    """İşlem detay sayfası"""
    transaction = SystemManager.get_transaction(transaction_id)

    if not transaction:
        flash('İşlem bulunamadı!', 'danger')
        return redirect(url_for('main.dashboard'))

    # İşlem geçmişini al
    transaction_history = SystemManager.get_transaction_history(transaction_id)

    # Müşteri bilgilerini al
    customer = Customer.query.get(transaction.customer_id)

    # İşlem türünü Türkçeye çevir
    transaction_type_tr = SystemManager.get_transaction_type_tr(transaction.transaction_type)

    return render_template(
        'transaction_detail.html',
        transaction=transaction,
        transaction_history=transaction_history,
        customer=customer,
        transaction_type_tr=transaction_type_tr
    )


@main_bp.route('/transactions/<int:transaction_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_transaction(transaction_id):
    """İşlem düzenleme sayfası"""
    transaction = SystemManager.get_transaction(transaction_id)

    if not transaction:
        flash('İşlem bulunamadı!', 'danger')
        return redirect(url_for('main.dashboard'))

    # Ayarları al
    settings = Setting.query.all()

    # Mevcut ayarın milyem değerini al
    setting = Setting.query.get(transaction.setting_id)
    setting_purity = setting.purity_per_thousand if hasattr(setting, 'purity_per_thousand') else 916

    # Ağırlık bilgisini al
    scale_manager = ScaleManager()
    if not scale_manager.scale:
        scale_manager.initialize(simulation_mode=True)
        scale_manager.start_monitoring()

    weight, is_valid = scale_manager.get_current_weight()

    if request.method == 'POST':
        transaction_type = request.form.get('transaction_type')
        product_description = request.form.get('product_description')
        gram = request.form.get('gram', type=float)
        setting_id = request.form.get('setting_id', type=int)
        purity_per_thousand = request.form.get('purity_per_thousand', type=int, default=setting_purity)
        labor_percentage = request.form.get('labor_percentage', type=float, default=0)
        notes = request.form.get('notes')

        if not transaction_type or not gram or not setting_id:
            flash('İşlem tipi, gram ve ayar değerleri gereklidir!', 'danger')
        else:
            try:
                # Has değeri hesapla
                pure_gold_weight = SystemManager.calculate_pure_gold_weight(gram, purity_per_thousand)

                # İşçilik has karşılığını hesapla
                labor_pure_gold = SystemManager.calculate_labor_pure_gold(gram, labor_percentage)

                # İşlemi düzenle
                edited_transaction = SystemManager.edit_customer_transaction(
                    transaction_id=transaction_id,
                    user_id=current_user.id,
                    transaction_type=transaction_type,
                    gram=gram,
                    setting_id=setting_id,
                    product_description=product_description,
                    purity_per_thousand=purity_per_thousand,
                    pure_gold_weight=pure_gold_weight,
                    labor_percentage=labor_percentage,
                    labor_pure_gold=labor_pure_gold,
                    notes=notes
                )

                if edited_transaction:
                    flash('İşlem başarıyla düzenlendi!', 'success')
                    return redirect(url_for('main.transaction_detail', transaction_id=edited_transaction.id))
                else:
                    flash('İşlem düzenlenemedi!', 'danger')

            except Exception as e:
                flash(f'Hata oluştu: {str(e)}', 'danger')
                print(f"İşlem düzenlenirken hata: {str(e)}")

    # İşlem türleri
    transaction_types = [
        {'value': 'PRODUCT_IN', 'label': 'Ürün Giriş (Müşteriden Al)'},
        {'value': 'PRODUCT_OUT', 'label': 'Ürün Çıkış (Müşteriye Ver)'},
        {'value': 'SCRAP_IN', 'label': 'Hurda Giriş (Müşteriden Al)'},
        {'value': 'SCRAP_OUT', 'label': 'Hurda Çıkış (Müşteriye Ver)'}
    ]

    return render_template(
        'transaction_edit.html',
        transaction=transaction,
        transaction_types=transaction_types,
        settings=settings,
        setting_purity=setting_purity,
        weight=weight,
        weight_valid=is_valid,
        now=datetime.utcnow()
    )