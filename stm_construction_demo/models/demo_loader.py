# -*- coding: utf-8 -*-
import base64
from odoo import api, fields, models, _
from odoo.tools.misc import file_open


class StmDemoLoader(models.TransientModel):
    _name = 'stm.demo.loader'
    _description = 'محمّل بيانات الديمو وتجهيز البروفة'

    last_result_html = fields.Html(
        string='ملخص آخر عملية',
        readonly=True,
        default=lambda self: self._default_summary_html(),
    )
    show_rehearsal_guide = fields.Boolean(default=True)

    @api.model
    def _default_summary_html(self):
        return (
            '<div dir="rtl" class="text-muted">'
            'اضغط <strong>«إعادة تحميل بيانات الديمو»</strong> لإنشاء/تحديث المشاريع الثلاثة، '
            'الـ 12 وحدة عقارية، العقود الـ 3، مستخلص العظم، المرفقات، والمستخدمين الثلاثة بشكل آمن بدون تكرار.'
            '</div>'
        )

    # ------------------------------------------------------------------
    # Idempotent Lookup / Creation Helpers
    # ------------------------------------------------------------------
    def _get_sar_currency(self):
        sar = self.env['res.currency'].with_context(active_test=False).search(
            [('name', '=', 'SAR')], limit=1
        )
        if sar:
            vals = {}
            if not sar.active:
                vals['active'] = True
            if sar.symbol != 'ر.س':
                vals['symbol'] = 'ر.س'
            if vals:
                sar.sudo().write(vals)
            return sar
        return self.env.company.currency_id

    def _ensure_sar_pricelist(self, sar, company):
        Pricelist = self.env['product.pricelist'].sudo()
        pl = Pricelist.search(
            [('currency_id', '=', sar.id), ('company_id', '=', company.id)],
            limit=1,
        )
        if not pl:
            pl = Pricelist.create({
                'name': 'قائمة أسعار المشاريع السعودية (SAR)',
                'currency_id': sar.id,
                'company_id': company.id,
            })
        return pl

    def _ensure_demo_users(self, company):
        Users = self.env['res.users'].sudo().with_context(no_reset_password=True)

        def _grp_ids(xml_ids):
            ids = []
            for xid in xml_ids:
                g = self.env.ref(xid, raise_if_not_found=False)
                if g:
                    ids.append((4, g.id))
            return ids

        specs = [
            (
                'site_engineer',
                'م. كريم — مهندس الموقع',
                'site_engineer@stm-demo.local',
                [
                    'base.group_user',
                    'project.group_project_user',
                    'stock.group_stock_user',
                    'hr.group_hr_user',
                    'stm_construction_demo.group_stm_site_engineer',
                ],
            ),
            (
                'project_manager',
                'م. طارق — مدير المشروع والعمليات',
                'project_manager@stm-demo.local',
                [
                    'base.group_user',
                    'project.group_project_manager',
                    'purchase.group_purchase_user',
                    'stock.group_stock_user',
                    'sales_team.group_sale_salesman_all_leads',
                    'hr.group_hr_user',
                    'stm_construction_demo.group_stm_project_manager',
                ],
            ),
            (
                'sales_finance',
                'أ. نورة — المبيعات والمالية',
                'sales_finance@stm-demo.local',
                [
                    'base.group_user',
                    'project.group_project_user',
                    'sales_team.group_sale_manager',
                    'account.group_account_manager',
                    'hr.group_hr_user',
                    'stm_construction_demo.group_stm_sales_finance',
                ],
            ),
        ]

        created_users = {}
        for login, name, email, grp_xml_ids in specs:
            user = Users.with_context(active_test=False).search([('login', '=', login)], limit=1)
            group_cmds = _grp_ids(grp_xml_ids)
            if not user:
                user = Users.create({
                    'name': name,
                    'login': login,
                    'email': email,
                    'password': '1',
                    'lang': 'ar_001',
                    'active': True,
                    'company_id': company.id,
                    'company_ids': [(4, company.id)],
                    'groups_id': group_cmds,
                })
            else:
                user.write({
                    'name': name,
                    'email': email,
                    'password': '1',
                    'lang': 'ar_001',
                    'active': True,
                    'company_id': company.id,
                    'company_ids': [(4, company.id)],
                    'groups_id': group_cmds,
                })
            created_users[login] = user
        return created_users

    def _ensure_partner(self, ref, name, **extra):
        Partner = self.env['res.partner'].sudo()
        partner = Partner.search([('ref', '=', ref)], limit=1)
        if not partner:
            partner = Partner.search([('name', '=', name)], limit=1)
        vals = {'ref': ref, 'name': name}
        vals.update(extra)
        if partner:
            partner.write(vals)
        else:
            partner = Partner.create(vals)
        return partner

    def _ensure_employee(self, name, job_title, company):
        Emp = self.env['hr.employee'].sudo()
        emp = Emp.search([('name', '=', name), ('company_id', '=', company.id)], limit=1)
        if not emp:
            emp = Emp.create({
                'name': name,
                'job_title': job_title,
                'company_id': company.id,
            })
        elif emp.job_title != job_title:
            emp.write({'job_title': job_title})
        return emp

    def _ensure_material_product(self, code, name, cost, categ):
        Tmpl = self.env['product.template'].sudo()
        tmpl = Tmpl.search([('default_code', '=', code)], limit=1)
        vals = {
            'name': name,
            'default_code': code,
            'type': 'consu',
            'is_storable': True,
            'sale_ok': False,
            'purchase_ok': True,
            'standard_price': cost,
            'list_price': cost,
            'categ_id': categ.id,
        }
        if tmpl:
            tmpl.write(vals)
        else:
            tmpl = Tmpl.create(vals)
        return tmpl.product_variant_id

    def _ensure_product_category(self, name, parent=False):
        Cat = self.env['product.category'].sudo()
        cat = Cat.search([('name', '=', name)], limit=1)
        if not cat:
            vals = {'name': name}
            if parent:
                vals['parent_id'] = parent.id
            cat = Cat.create(vals)
        return cat

    def _ensure_unit_product(self, code, name, categ, vals):
        Tmpl = self.env['product.template'].sudo()
        tmpl = Tmpl.search([('default_code', '=', code)], limit=1)
        base_vals = {
            'name': name,
            'default_code': code,
            'type': 'consu',
            'is_storable': True,
            'sale_ok': True,
            'purchase_ok': False,
            'categ_id': categ.id,
            'stm_is_real_estate_unit': True,
        }
        base_vals.update(vals)
        if tmpl:
            tmpl.write(base_vals)
        else:
            tmpl = Tmpl.create(base_vals)
        return tmpl

    def _read_porcelain_contract_b64(self):
        with file_open('stm_construction_demo/data/demo_assets/subcontract_porcelain_contract.docx', 'rb') as fp:
            return base64.b64encode(fp.read())

    # ------------------------------------------------------------------
    # Main Idempotent Demo Data Loader (T4.1 + T4.2)
    # ------------------------------------------------------------------
    def action_load_demo_data(self):
        self.ensure_one()
        company = self.env.company
        sar = self._get_sar_currency()
        sar_pricelist = self._ensure_sar_pricelist(sar, company)

        # 1. Three Demo Users (T4.2)
        users = self._ensure_demo_users(company)
        u_eng = users['site_engineer']
        u_pm = users['project_manager']
        u_fin = users['sales_finance']

        # 2. Partners & Crew Employees
        vnd_porcelain = self._ensure_partner(
            'STM-VND-01', 'صفي الله فيض محمد خان (مقاول واجهات وبلاط)',
            supplier_rank=1, phone='+966 50 412 8890', city='جدة',
        )
        vnd_bone = self._ensure_partner(
            'STM-VND-02', 'شركة رواسي الخليج للعظم والإنشاءات',
            supplier_rank=1, is_company=True, phone='+966 12 655 3200', city='جدة',
        )
        vnd_materials = self._ensure_partner(
            'STM-VND-03', 'مؤسسة النور لمواد البناء',
            supplier_rank=1, is_company=True, phone='+966 12 688 9100', city='جدة',
        )

        p_owner = self._ensure_partner(
            'STM-OWN-01', 'شركة إشراقات الحجاز للتطوير العقاري',
            customer_rank=1, is_company=True, phone='+966 12 601 4400', city='جدة',
        )
        p_consultant = self._ensure_partner(
            'STM-CON-01', 'مكتب الأفق للاستشارات الهندسية',
            is_company=True, phone='+966 12 612 7700', city='جدة',
        )
        p_designer = self._ensure_partner(
            'STM-DES-01', 'مكتب العمران للتصميم المعماري',
            is_company=True, phone='+966 11 450 2200', city='الرياض',
        )
        p_insurance = self._ensure_partner(
            'STM-INS-01', 'شركة التعاونية للتأمين',
            is_company=True, phone='+966 11 252 5800', city='الرياض',
        )
        p_authority = self._ensure_partner(
            'STM-AUT-01', 'أمانة محافظة جدة',
            is_company=True, city='جدة',
        )

        buyer_1 = self._ensure_partner('STM-BUY-01', 'خالد العتيبي', customer_rank=1, phone='+966 50 311 4401', city='الرياض')
        buyer_2 = self._ensure_partner('STM-BUY-02', 'فهد القحطاني', customer_rank=1, phone='+966 55 782 1190', city='الرياض')
        buyer_3 = self._ensure_partner('STM-BUY-03', 'سارة الغامدي', customer_rank=1, phone='+966 54 902 3315', city='جدة')
        buyer_4 = self._ensure_partner('STM-BUY-04', 'عبدالرحمن الشهري', customer_rank=1, phone='+966 56 224 7781', city='الرياض')

        emp_pm = self._ensure_employee('م. طارق المنصور', 'مدير المشروع والعمليات', company)
        emp_eng = self._ensure_employee('م. كريم السيد', 'مهندس المشروع / الموقع', company)
        emp_sup = self._ensure_employee('أ. سامي الحربي', 'مشرف المشروع', company)

        # 3. Materials Category & Products
        mat_cat = self._ensure_product_category('مواد البناء والإنشاءات')
        prod_steel = self._ensure_material_product('STM-MAT-STEEL16', 'حديد تسليح 16مم (طن)', 2850.0, mat_cat)
        prod_cement = self._ensure_material_product('STM-MAT-CEMENT', 'أسمنت بورتلاندي مقاوم (كيس 50 كجم)', 18.5, mat_cat)
        prod_porcelain = self._ensure_material_product('STM-MAT-PORCELAIN', 'بورسلان واجهات فاخر 60×120 (م²)', 95.0, mat_cat)

        porcelain_b64 = self._read_porcelain_contract_b64()

        Boq = self.env['construction.boq'].sudo()
        Stage = self.env['project.task.type'].sudo()

        # ------------------------------------------------------------------
        # STORY 3 — Contracting: مشروع إشراقات الحجاز — مخطط شمس العروس 1 (BOQ/2026/0001)
        # ------------------------------------------------------------------
        boq1 = Boq.search([('name', '=', 'BOQ/2026/0001')], limit=1)
        boq1_vals = {
            'name': 'BOQ/2026/0001',
            'project_name': 'مشروع إشراقات الحجاز — مخطط شمس العروس 1',
            'project_type': 'contracting',
            'location': 'جدة — مخطط شمس العروس 1',
            'company_id': company.id,
            'currency_id': sar.id,
            'date_start_planned': '2026-01-15',
            'date_start_actual': '2026-01-15',
            'date_end_planned': '2026-12-30',
            'date_end_expected': '2026-12-30',
            'delay_days': 0,
            'delay_reason': False,
            'land_area': 1200.0,
            'building_area': 850.0,
            'total_built_area': 4800.0,
            'floors_count': 6,
            'residential_units_count': 18,
            'commercial_shops_count': 4,
            'parking_slots_count': 24,
            'electricity_meters_count': 22,
            'owner_id': p_owner.id,
            'consultant_id': p_consultant.id,
            'designer_id': p_designer.id,
            'insurance_company_id': p_insurance.id,
            'official_authority_id': p_authority.id,
            'vendor_ids': [(6, 0, [vnd_porcelain.id, vnd_bone.id, vnd_materials.id])],
            'project_manager_id': emp_pm.id,
            'project_engineer_id': emp_eng.id,
            'supervisor_id': emp_sup.id,
            'technicians_count': 14,
            'workers_count': 42,
            'equipment_summary': 'رافعة برجية (1)، مضخة خرسانة (1)، بوكلين وحفار (2)، هزازات خرسانة (4)، سقالات معدنية كاملة للواجهات.',
            'notes': '<p>مشروع مقاولات للغير لصالح شركة إشراقات الحجاز للتطوير العقاري — يشمل العظم والتشطيبات والواجهات وفق المخططات المعتمدة.</p>',
        }
        if boq1:
            boq1.write(boq1_vals)
        else:
            boq1 = Boq.create(boq1_vals)

        if not boq1.line_ids:
            # 21 standard scope items totaling ~ 4,200,000 SAR planned, ~ 2,520,000 actual, ~ 62% progress
            boq1_lines_spec = [
                ('excavation', 'حفر وردم وتأسيس الموقع', 'م³', 1800, 75.0, 135000, 0, 0, 100.0, 3, False),
                ('structure', 'أعمال العظم والخرسانة المسلحة', 'م²', 4800, 225.0, 920000, 120000, 160000, 85.0, 1, False),
                ('masonry', 'أعمال المباني والبلوك', 'م²', 3200, 65.0, 145000, 20000, 63000, 70.0, 1, False),
                ('plastering', 'أعمال اللياسة الداخلية والخارجية', 'م²', 6000, 35.0, 110000, 30000, 100000, 55.0, 1, False),
                ('insulation', 'أعمال العزل المائي والحراري', 'م²', 2400, 50.0, 85000, 10000, 35000, 70.0, 1, False),
                ('electrical', 'التمديدات واللوحات الكهربائية', 'مقطوعة', 1, 240000.0, 140000, 40000, 100000, 60.0, 1, False),
                ('hvac', 'أعمال التكييف والتهوية المركزية', 'مقطوعة', 1, 260000.0, 115000, 65000, 145000, 45.0, 1, False),
                ('plumbing', 'أعمال السباكة والتغذية والصرف', 'مقطوعة', 1, 180000.0, 125000, 25000, 55000, 70.0, 1, False),
                ('safety', 'أنظمة الأمن والسلامة والدفاع المدني', 'مقطوعة', 1, 95000.0, 40000, 20000, 55000, 45.0, 1, False),
                ('tiling', 'أعمال البلاط والأرضيات', 'م²', 3500, 80.0, 110000, 50000, 170000, 40.0, 1, False),
                ('irrigation', 'شبكة الري الحديثة', 'مقطوعة', 1, 35000.0, 10000, 5000, 25000, 30.0, 1, False),
                ('painting', 'أعمال الدهانات والديكور', 'م²', 5500, 28.0, 45000, 25000, 109000, 30.0, 1, False),
                ('windows', 'أعمال الألمنيوم والشبابيك', 'م²', 650, 200.0, 50000, 40000, 80000, 40.0, 1, False),
                ('doors', 'الأبواب الخشبية والمصفحة', 'عدد', 90, 1200.0, 35000, 35000, 73000, 35.0, 1, False),
                ('ceilings', 'الأسقف المستعارة والجبس بورد', 'م²', 2800, 45.0, 45000, 20000, 81000, 35.0, 1, False),
                ('elevators', 'توريد وتركيب المصاعد', 'عدد', 2, 110000.0, 110000, 75000, 110000, 50.0, 1, False),
                ('epoxy', 'أعمال الإيبوكسي للمواقف والخزانات', 'م²', 1000, 65.0, 25000, 15000, 40000, 40.0, 1, False),
                ('agriculture', 'أعمال الزراعة والتشجير', 'م²', 400, 90.0, 10000, 5000, 26000, 30.0, 1, False),
                ('landscape', 'لاندسكيب (مناطق خضراء - مسبح - جلسات - ممرات رياضة)', 'م²', 500, 150.0, 20000, 15000, 55000, 25.0, 1, False),
                ('facades', 'تركيب واجهات البورسلان — 10,000 م²', 'م²', 10000, 72.0, 225000, 145000, 175000, 50.0, 3, False),
                ('other', 'أمر تغييري — توسعة وتكسية مدخل المشروع', 'مقطوعة', 1, 70000.0, 20000, 20000, 50000, 30.0, 1, True),
            ]
            line_cmds = []
            seq = 10
            for cat, desc, uom, qty, price, act, comm, etc, prog, sub_cnt, is_vo in boq1_lines_spec:
                line_cmds.append((0, 0, {
                    'sequence': seq,
                    'included': True,
                    'is_variation_order': is_vo,
                    'scope_category': cat,
                    'name': desc,
                    'uom_name': uom,
                    'planned_qty': qty,
                    'unit_price': price,
                    'actual_amount': act,
                    'committed_amount': comm,
                    'etc_amount': etc,
                    'progress_percent': prog,
                    'subtasks_count': sub_cnt,
                }))
                seq += 10
            boq1.write({'line_ids': line_cmds})

        if not boq1.document_line_ids:
            boq1.action_populate_standard_documents()
        for idx, doc in enumerate(boq1.document_line_ids):
            if doc.category == 'subcontract' or 'عقود مقاولي الباطن' in (doc.name or ''):
                doc.write({
                    'status': 'approved',
                    'attachment_file': porcelain_b64,
                    'attachment_filename': 'نموذج عقد بلاط.docx',
                    'notes': 'عقد تركيب واجهات بورسلان — المقاول صفي الله فيض محمد خان — 72 ر.س/م² — ضمان حسن تنفيذ 10%',
                })
            elif idx < 12 and doc.status == 'pending':
                doc.write({'status': 'approved'})

        if not boq1.project_id:
            boq1.action_confirm_create_project()
        boq1.write({'state': 'in_progress'})
        if boq1.project_id:
            boq1.project_id.write({'stm_progress_planned': 65.0})

        # Vendor Progress Certificate (CERT/V/2026/001 — جاري رقم / 12 matching نموذج مستخلص عظم.xlsx)
        Cert = self.env['construction.certificate'].sudo()
        cert_v = Cert.search([('name', '=', 'CERT/V/2026/001')], limit=1)
        cert_v_vals = {
            'name': 'CERT/V/2026/001',
            'certificate_no': 'جاري رقم / 12',
            'certificate_type': 'vendor',
            'project_id': boq1.project_id.id,
            'boq_id': boq1.id,
            'partner_id': vnd_bone.id,
            'work_scope': 'مصنعية أعمال العظم',
            'date': '2026-10-27',
            'company_id': company.id,
            'currency_id': sar.id,
            'bank_name': 'مصرف الراجحي',
            'bank_account_no': '214608010459821',
            'iban': 'SA4480000214608010459821',
            'contract_ref': 'CNT-SUB-2026-012 / عقد مصنعية عظم',
            'subcontract_file': porcelain_b64,
            'subcontract_filename': 'نموذج عقد بلاط.docx',
            'retention_percent': 10.0,
            'deduction_prev': 650.0,
            'deduction_curr': 0.0,
            'previously_paid': 595500.0,
            'notes': 'مستخلص مطابق لنموذج مستخلص عظم.xlsx — جاهز لإنشاء مسودة فاتورة مورد في قسم المحاسبة.',
        }
        if cert_v:
            cert_v.write(cert_v_vals)
        else:
            cert_v = Cert.create(cert_v_vals)

        if not cert_v.line_ids:
            bone_lines = [
                # Section 1
                (0, 0, {'sequence': 10, 'display_type': 'line_section', 'item_code': '1', 'name': '1. أعمال النجارة المسلحة'}),
                (0, 0, {'sequence': 20, 'item_code': '1', 'name': 'بعد صب اللبشة', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 38000, 'prev_qty': 1, 'curr_qty': 0}),
                (0, 0, {'sequence': 30, 'item_code': '2', 'name': 'بعد صب الميد المسلحة + أرضيات المواقف', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 28500, 'prev_qty': 1, 'curr_qty': 0}),
                (0, 0, {'sequence': 40, 'item_code': '3', 'name': 'بعد صب سقف + عمود المواقف', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 95000, 'prev_qty': 1, 'curr_qty': 0}),
                (0, 0, {'sequence': 50, 'item_code': '4', 'name': 'بعد صب سقف + عمود الدور الأول', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 83000, 'prev_qty': 1, 'curr_qty': 0}),
                (0, 0, {'sequence': 60, 'item_code': '5', 'name': 'بعد صب سقف + عمود الدور الثاني', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 83000, 'prev_qty': 1, 'curr_qty': 0}),
                (0, 0, {'sequence': 70, 'item_code': '6', 'name': 'بعد صب سقف + عمود الدور الثالث', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 100000, 'prev_qty': 1, 'curr_qty': 0}),
                (0, 0, {'sequence': 80, 'item_code': '7', 'name': 'بعد صب سقف + عمود الدور الرابع', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 100000, 'prev_qty': 1, 'curr_qty': 0}),
                (0, 0, {'sequence': 90, 'item_code': '8', 'name': 'بعد صب سقف + عمود الدور الخامس', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 100000, 'prev_qty': 1, 'curr_qty': 0}),
                (0, 0, {'sequence': 100, 'item_code': '9', 'name': 'بعد صب سقف + عمود الدور السادس', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 100000, 'prev_qty': 0, 'curr_qty': 0}),
                (0, 0, {'sequence': 110, 'item_code': '10', 'name': 'بعد صب سقف + عمود الدور الملحق', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 88000, 'prev_qty': 0, 'curr_qty': 0}),
                (0, 0, {'sequence': 120, 'item_code': '11', 'name': 'بعد مباني دور المواقف', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 9500, 'prev_qty': 0, 'curr_qty': 0}),
                (0, 0, {'sequence': 130, 'item_code': '12', 'name': 'بعد مباني الدور الأول', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 30000, 'prev_qty': 1, 'curr_qty': 0}),
                (0, 0, {'sequence': 140, 'item_code': '13', 'name': 'بعد مباني الدور الثاني', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 30000, 'prev_qty': 1, 'curr_qty': 0}),
                (0, 0, {'sequence': 150, 'item_code': '14', 'name': 'بعد مباني الدور الثالث', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 30000, 'prev_qty': 0.5, 'curr_qty': 0.5}),
                (0, 0, {'sequence': 160, 'item_code': '15', 'name': 'بعد مباني الدور الرابع', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 30000, 'prev_qty': 0, 'curr_qty': 0}),
                (0, 0, {'sequence': 170, 'item_code': '16', 'name': 'بعد مباني الدور الخامس', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 30000, 'prev_qty': 0, 'curr_qty': 0}),
                (0, 0, {'sequence': 180, 'item_code': '17', 'name': 'بعد مباني الدور السادس', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 30000, 'prev_qty': 0, 'curr_qty': 0}),
                (0, 0, {'sequence': 190, 'item_code': '18', 'name': 'بعد مباني الدور الملحق', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 30000, 'prev_qty': 0, 'curr_qty': 0}),
                (0, 0, {'sequence': 200, 'item_code': '19', 'name': 'بعد صب سقف المصعد وبيت الدرج والسترة ومبانيها', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 15000, 'prev_qty': 0, 'curr_qty': 0}),
                # Section 2
                (0, 0, {'sequence': 210, 'display_type': 'line_section', 'item_code': '2', 'name': '2. الأعمال الملحقة بالعقد'}),
                (0, 0, {'sequence': 220, 'item_code': '1', 'name': 'خزانات مياه', 'uom_name': 'م1', 'contract_qty': 300, 'unit_price': 95, 'prev_qty': 300, 'curr_qty': 0}),
                (0, 0, {'sequence': 230, 'item_code': '2', 'name': 'البيارة', 'uom_name': 'م2', 'contract_qty': 0, 'unit_price': 0, 'prev_qty': 0, 'curr_qty': 0}),
                (0, 0, {'sequence': 240, 'item_code': '3', 'name': 'الأمتار الطولية للسور', 'uom_name': 'م.ط', 'contract_qty': 50, 'unit_price': 90, 'prev_qty': 50, 'curr_qty': 0}),
                (0, 0, {'sequence': 250, 'item_code': '4', 'name': 'الأمتار الطولية للسترة', 'uom_name': 'م.ط', 'contract_qty': 0, 'unit_price': 45, 'prev_qty': 0, 'curr_qty': 0}),
            ]
            cert_v.write({'line_ids': bone_lines})

        if not cert_v.move_id and cert_v.state in ('draft', 'site_engineer', 'rejected'):
            cert_v.write({
                'state': 'pm_approved',
                'site_engineer_id': u_eng.id,
                'pm_approved_by_id': u_pm.id,
                'rejection_reason': False,
            })

        # Customer Progress Certificate (CERT/C/2026/001 — linked to real draft Customer Invoice)
        cert_c = Cert.search([('name', '=', 'CERT/C/2026/001')], limit=1)
        cert_c_vals = {
            'name': 'CERT/C/2026/001',
            'certificate_no': 'مستخلص عميل رقم / 1',
            'certificate_type': 'customer',
            'project_id': boq1.project_id.id,
            'boq_id': boq1.id,
            'partner_id': p_owner.id,
            'work_scope': 'أعمال العظم والمباني — دفعة تعاقدية رقم 1',
            'date': '2026-11-01',
            'company_id': company.id,
            'currency_id': sar.id,
            'contract_ref': 'CNT-CLIENT-SHAMS-01',
            'retention_percent': 10.0,
            'notes': 'مستخلص عميل خارجي لمشروع إشراقات الحجاز — مرتبط بمسودة فاتورة عميل في المحاسبة.',
        }
        if cert_c:
            cert_c.write(cert_c_vals)
        else:
            cert_c = Cert.create(cert_c_vals)

        if not cert_c.line_ids:
            cert_c.write({
                'line_ids': [
                    (0, 0, {'sequence': 10, 'item_code': '1', 'name': 'أعمال الحفر والأساسات', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 300000, 'prev_qty': 1.0, 'curr_qty': 0.0}),
                    (0, 0, {'sequence': 20, 'item_code': '2', 'name': 'أعمال الهيكل الإنشائي والعظم', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 700000, 'prev_qty': 0.2143, 'curr_qty': 0.2857}),
                    (0, 0, {'sequence': 30, 'item_code': '3', 'name': 'أعمال المباني والعزل', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 300000, 'prev_qty': 0.0, 'curr_qty': 0.333333}),
                    (0, 0, {'sequence': 40, 'item_code': '4', 'name': 'أعمال الواجهات والبورسلان', 'uom_name': 'مقطوعة', 'contract_qty': 1, 'unit_price': 200000, 'prev_qty': 0.0, 'curr_qty': 0.0}),
                ]
            })
        if not cert_c.move_id:
            cert_c.write({
                'state': 'pm_approved',
                'site_engineer_id': u_eng.id,
                'pm_approved_by_id': u_pm.id,
            })
            cert_c.action_create_account_move()

        # 3 Site Material Requests linked to boq1.project_id (A01)
        SiteReq = self.env['construction.site.request'].sudo()
        srq1 = SiteReq.search([('name', '=', 'SRQ/2026/0001')], limit=1)
        if not srq1:
            srq1 = SiteReq.create({
                'name': 'SRQ/2026/0001',
                'project_id': boq1.project_id.id,
                'boq_id': boq1.id,
                'requested_by_id': u_eng.id,
                'request_date': '2026-10-15',
                'delivery_mode': 'from_main_wh',
                'currency_id': sar.id,
                'notes': 'نقل مخزني من المخزن الرئيسي إلى موقع مشروع إشراقات الحجاز (نقل عهدة موقع — ليس استهلاكاً).',
                'line_ids': [
                    (0, 0, {'product_id': prod_steel.id, 'description': prod_steel.display_name, 'qty': 20.0, 'uom_id': prod_steel.uom_id.id, 'estimated_unit_cost': 2850.0}),
                    (0, 0, {'product_id': prod_cement.id, 'description': prod_cement.display_name, 'qty': 300.0, 'uom_id': prod_cement.uom_id.id, 'estimated_unit_cost': 18.5}),
                ],
            })
        if srq1.state in ('draft', 'submitted'):
            srq1.write({'state': 'approved', 'approved_by_id': u_pm.id})
        if srq1.state == 'approved' and not srq1.picking_id:
            srq1.action_create_stock_picking()

        srq2 = SiteReq.search([('name', '=', 'SRQ/2026/0002')], limit=1)
        if not srq2:
            srq2 = SiteReq.create({
                'name': 'SRQ/2026/0002',
                'project_id': boq1.project_id.id,
                'boq_id': boq1.id,
                'requested_by_id': u_eng.id,
                'request_date': '2026-10-20',
                'delivery_mode': 'site_consumption',
                'currency_id': sar.id,
                'notes': 'صرف استهلاك فعلي لأعمال صب الأعمدة والمباني بالدور الثالث.',
                'line_ids': [
                    (0, 0, {'product_id': prod_cement.id, 'description': prod_cement.display_name, 'qty': 150.0, 'uom_id': prod_cement.uom_id.id, 'estimated_unit_cost': 18.5}),
                ],
            })
        if srq2.state in ('draft', 'submitted'):
            srq2.write({'state': 'approved', 'approved_by_id': u_pm.id})
        if srq2.state == 'approved' and not srq2.picking_id:
            srq2.action_create_stock_picking()

        srq3 = SiteReq.search([('name', '=', 'SRQ/2026/0003')], limit=1)
        if not srq3:
            srq3 = SiteReq.create({
                'name': 'SRQ/2026/0003',
                'project_id': boq1.project_id.id,
                'boq_id': boq1.id,
                'requested_by_id': u_eng.id,
                'request_date': '2026-11-22',
                'vendor_id': vnd_materials.id,
                'delivery_mode': 'direct_site',
                'currency_id': sar.id,
                'state': 'submitted',
                'notes': 'طلب توريد مباشر للواجهات — بانتظار اعتماد مدير المشروع أو رفضه أثناء العرض الحي.',
                'line_ids': [
                    (0, 0, {'product_id': prod_porcelain.id, 'description': prod_porcelain.display_name, 'qty': 450.0, 'uom_id': prod_porcelain.uom_id.id, 'estimated_unit_cost': 95.0}),
                ],
            })

        # ------------------------------------------------------------------
        # STORY 1 — Off-Plan: أبراج إشراقات السكنية — بلوك A (BOQ/2026/0002)
        # ------------------------------------------------------------------
        boq2 = Boq.search([('name', '=', 'BOQ/2026/0002')], limit=1)
        boq2_vals = {
            'name': 'BOQ/2026/0002',
            'project_name': 'أبراج إشراقات السكنية — بلوك A (10 وحدات)',
            'project_type': 'off_plan',
            'location': 'جدة — حي الشاطئ',
            'company_id': company.id,
            'currency_id': sar.id,
            'date_start_planned': '2026-02-01',
            'date_start_actual': '2026-02-05',
            'date_end_planned': '2026-11-15',
            'date_end_expected': '2026-11-27',
            'delay_days': 12,
            'delay_reason': 'تأخر توريد شحنة البورسلان الخارجي من الميناء',
            'land_area': 950.0,
            'building_area': 650.0,
            'total_built_area': 2900.0,
            'floors_count': 4,
            'residential_units_count': 10,
            'commercial_shops_count': 0,
            'parking_slots_count': 12,
            'electricity_meters_count': 11,
            'owner_id': p_owner.id,
            'consultant_id': p_consultant.id,
            'designer_id': p_designer.id,
            'insurance_company_id': p_insurance.id,
            'vendor_ids': [(6, 0, [vnd_porcelain.id, vnd_bone.id])],
            'project_manager_id': emp_pm.id,
            'project_engineer_id': emp_eng.id,
            'supervisor_id': emp_sup.id,
            'technicians_count': 10,
            'workers_count': 28,
            'equipment_summary': 'ونش رفع مواد (1)، سقالات واجهات كاملة، مضخة خرسانة متنقلة.',
            'notes': '<p>مشروع بيع على الخارطة (10 وحدات) — مفعّل به سيناريو الإنذار المبكر للتكلفة (70% إنجاز مقابل 90% صرف) وتأخير 12 يوماً في الواجهات.</p>',
        }
        if boq2:
            boq2.write(boq2_vals)
        else:
            boq2 = Boq.create(boq2_vals)

        if not boq2.line_ids:
            # Exact math: Total Planned=3,000,000 | Actual=2,700,000 (90%) | ETC=600,000 -> EAC=3,300,000 | Weighted Progress=70.0%
            boq2_lines_spec = [
                ('excavation', 'حفر وردم وتأسيس البلوك', 'مقطوعة', 1, 300000.0, 285000.0, 0.0, 0.0, 100.0, 1),
                ('structure', 'أعمال العظم والخرسانة', 'مقطوعة', 1, 1100000.0, 1045000.0, 50000.0, 115000.0, 90.0, 1),
                ('masonry', 'أعمال المباني واللياسة والعزل', 'مقطوعة', 1, 500000.0, 470000.0, 30000.0, 80000.0, 80.0, 1),
                ('electrical', 'أعمال الكهرباء والسباكة والتكييف', 'مقطوعة', 1, 500000.0, 460000.0, 60000.0, 140000.0, 60.0, 1),
                ('facades', 'تركيب واجهات البورسلان', 'م²', 4000, 100.0, 320000.0, 90000.0, 165000.0, 25.0, 3),
                ('other', 'تشطيبات نهائية ومصاعد', 'مقطوعة', 1, 200000.0, 120000.0, 50000.0, 100000.0, 5.0, 1),
            ]
            line_cmds = []
            seq = 10
            for cat, desc, uom, qty, price, act, comm, etc, prog, sub_cnt in boq2_lines_spec:
                line_cmds.append((0, 0, {
                    'sequence': seq,
                    'included': True,
                    'scope_category': cat,
                    'name': desc,
                    'uom_name': uom,
                    'planned_qty': qty,
                    'unit_price': price,
                    'actual_amount': act,
                    'committed_amount': comm,
                    'etc_amount': etc,
                    'progress_percent': prog,
                    'subtasks_count': sub_cnt,
                }))
                seq += 10
            boq2.write({'line_ids': line_cmds})

        if not boq2.project_id:
            boq2.action_confirm_create_project()
        boq2.write({'state': 'in_progress'})
        if boq2.project_id:
            boq2.project_id.write({
                'stm_progress_planned': 82.0,
                'stm_delay_days': 12,
                'stm_delay_reason': 'تأخر توريد شحنة البورسلان الخارجي من الميناء',
            })
            delayed_stage = Stage.search([('name', '=', 'متأخر')], limit=1)
            facades_task = self.env['project.task'].sudo().search([
                ('project_id', '=', boq2.project_id.id),
                ('parent_id', '=', False),
                ('name', 'ilike', 'واجهات البورسلان'),
            ], limit=1)
            if facades_task:
                t_vals = {
                    'stm_is_delayed': True,
                    'stm_delay_days': 12,
                    'stm_delay_reason': 'تأخر توريد شحنة البورسلان الخارجي من الميناء',
                }
                if delayed_stage:
                    t_vals['stage_id'] = delayed_stage.id
                facades_task.write(t_vals)

        # Featured 10-Unit Block Cost Card (linked to Story 1 Off-Plan project)
        UnitCost = self.env['construction.unit.cost'].sudo()
        uc = UnitCost.search([('name', '=', 'بلوك إشراقات السكني — 10 وحدات')], limit=1)
        uc_vals = {
            'name': 'بلوك إشراقات السكني — 10 وحدات',
            'project_id': boq2.project_id.id,
            'company_id': company.id,
            'currency_id': sar.id,
            'is_featured': True,
            'units_count': 10,
            'block_budget': 3000000.0,
            'block_actual': 1800000.0,
            'block_etc': 1500000.0,
            'unit_net_sale_price': 400000.0,
            'unit_cash_collected': 100000.0,
            'accounting_note': 'ملاحظة محاسبية: التحصيل النقدي لا يساوي ربحاً محققاً (الأرقام قبل الضرائب).',
        }
        if uc:
            uc.write(uc_vals)
        else:
            uc = UnitCost.create(uc_vals)

        # 6 Off-Plan Units (Story 1)
        off_cat = self._ensure_product_category('أبراج إشراقات السكنية — بلوك A')
        off_units_spec = [
            ('STM-OFF-A101', 'شقة A101 — أبراج إشراقات (على الخارطة)', 'A101', 'sold'),
            ('STM-OFF-A102', 'شقة A102 — أبراج إشراقات (على الخارطة)', 'A102', 'sold'),
            ('STM-OFF-A103', 'شقة A103 — أبراج إشراقات (على الخارطة)', 'A103', 'reserved'),
            ('STM-OFF-A104', 'شقة A104 — أبراج إشراقات (على الخارطة)', 'A104', 'reserved'),
            ('STM-OFF-A105', 'شقة A105 — أبراج إشراقات (على الخارطة)', 'A105', 'available'),
            ('STM-OFF-A106', 'شقة A106 — أبراج إشراقات (على الخارطة)', 'A106', 'available'),
        ]
        unit_tmpls = {}
        for code, uname, unit_no, avail in off_units_spec:
            unit_tmpls[code] = self._ensure_unit_product(code, uname, off_cat, {
                'stm_project_id': boq2.project_id.id,
                'stm_unit_cost_id': uc.id,
                'stm_unit_availability': avail,
                'stm_handover_readiness': 'under_construction',
                'stm_expected_handover_date': '2027-06-30',
                'project_location': 'جدة — حي الشاطئ',
                'project_type': 'بيع على الخارطة',
                'building_no': 'بلوك A',
                'unit_no': unit_no,
                'unit_area': '145 م²',
                'total_building_area': 145.0,
                'cash_meter_price': 2758.62,
                'total_cash_price': 400000.0,
                'installment_meter_price': 2965.52,
                'total_installment_price': 430000.0,
                'list_price': 400000.0,
                'garage_yes_no': True,
            })

        # ------------------------------------------------------------------
        # STORY 2 — Ready Units: كمباوند الياسمين — وحدات جاهزة للتسليم (BOQ/2026/0003)
        # ------------------------------------------------------------------
        boq3 = Boq.search([('name', '=', 'BOQ/2026/0003')], limit=1)
        boq3_vals = {
            'name': 'BOQ/2026/0003',
            'project_name': 'كمباوند الياسمين — وحدات جاهزة للتسليم',
            'project_type': 'ready',
            'location': 'الرياض — حي الياسمين',
            'company_id': company.id,
            'currency_id': sar.id,
            'date_start_planned': '2025-09-01',
            'date_start_actual': '2025-09-01',
            'date_end_planned': '2026-10-15',
            'date_end_expected': '2026-10-15',
            'delay_days': 0,
            'delay_reason': False,
            'land_area': 1600.0,
            'building_area': 1050.0,
            'total_built_area': 3600.0,
            'floors_count': 3,
            'residential_units_count': 6,
            'commercial_shops_count': 0,
            'parking_slots_count': 12,
            'electricity_meters_count': 7,
            'owner_id': p_owner.id,
            'consultant_id': p_consultant.id,
            'project_manager_id': emp_pm.id,
            'project_engineer_id': emp_eng.id,
            'supervisor_id': emp_sup.id,
            'technicians_count': 8,
            'workers_count': 20,
            'equipment_summary': 'أعمال مكتملة — فرق اختبارات التشغيل والتسليم النهائي.',
            'notes': '<p>مشروع وحدات سكنية جاهزة للتسليم الفوري في حي الياسمين بالرياض.</p>',
        }
        if boq3:
            boq3.write(boq3_vals)
        else:
            boq3 = Boq.create(boq3_vals)

        if not boq3.line_ids:
            boq3_lines_spec = [
                ('excavation', 'الحفر والأساسات', 'مقطوعة', 1, 250000.0, 245000.0, 0.0, 100.0),
                ('structure', 'الهيكل الخرساني والعظم', 'مقطوعة', 1, 850000.0, 835000.0, 0.0, 100.0),
                ('masonry', 'المباني واللياسة والعزل', 'مقطوعة', 1, 400000.0, 390000.0, 0.0, 100.0),
                ('electrical', 'الأعمال الكهروميكانيكية', 'مقطوعة', 1, 420000.0, 410000.0, 0.0, 100.0),
                ('tiling', 'التشطيبات والأرضيات', 'مقطوعة', 1, 320000.0, 305000.0, 0.0, 100.0),
                ('facades', 'الواجهات واللاندسكيب', 'مقطوعة', 1, 160000.0, 155000.0, 0.0, 100.0),
            ]
            line_cmds = []
            seq = 10
            for cat, desc, uom, qty, price, act, etc, prog in boq3_lines_spec:
                line_cmds.append((0, 0, {
                    'sequence': seq,
                    'included': True,
                    'scope_category': cat,
                    'name': desc,
                    'uom_name': uom,
                    'planned_qty': qty,
                    'unit_price': price,
                    'actual_amount': act,
                    'etc_amount': etc,
                    'progress_percent': prog,
                }))
                seq += 10
            boq3.write({'line_ids': line_cmds})

        if not boq3.project_id:
            boq3.action_confirm_create_project()
        boq3.write({'state': 'done'})
        if boq3.project_id:
            boq3.project_id.write({'stm_progress_planned': 100.0})

        # 6 Ready Units (Story 2 — total 12 new demo units!)
        rdy_cat = self._ensure_product_category('كمباوند الياسمين — وحدات جاهزة')
        rdy_units_spec = [
            ('STM-RDY-Y201', 'فيلا Y201 — كمباوند الياسمين (جاهزة)', 'Y201', 'sold', 'handed_over', 550000.0, '180 م²', 180.0),
            ('STM-RDY-Y202', 'فيلا Y202 — كمباوند الياسمين (جاهزة)', 'Y202', 'sold', 'ready', 580000.0, '190 م²', 190.0),
            ('STM-RDY-Y203', 'فيلا Y203 — كمباوند الياسمين (جاهزة)', 'Y203', 'available', 'ready', 560000.0, '185 م²', 185.0),
            ('STM-RDY-Y204', 'فيلا Y204 — كمباوند الياسمين (جاهزة)', 'Y204', 'reserved', 'ready', 600000.0, '200 م²', 200.0),
            ('STM-RDY-Y205', 'فيلا Y205 — كمباوند الياسمين (جاهزة)', 'Y205', 'available', 'ready', 590000.0, '195 م²', 195.0),
            ('STM-RDY-Y206', 'فيلا Y206 — كمباوند الياسمين (جاهزة)', 'Y206', 'available', 'ready', 620000.0, '210 م²', 210.0),
        ]
        for code, uname, unit_no, avail, ready_state, price, area_txt, area_num in rdy_units_spec:
            unit_tmpls[code] = self._ensure_unit_product(code, uname, rdy_cat, {
                'stm_project_id': boq3.project_id.id,
                'stm_unit_availability': avail,
                'stm_handover_readiness': ready_state,
                'stm_expected_handover_date': '2026-12-01' if ready_state != 'handed_over' else '2026-11-10',
                'project_location': 'الرياض — حي الياسمين',
                'project_type': 'وحدات جاهزة',
                'building_no': 'كمباوند الياسمين',
                'unit_no': unit_no,
                'unit_area': area_txt,
                'total_building_area': area_num,
                'cash_meter_price': round(price / area_num, 2),
                'total_cash_price': price,
                'installment_meter_price': round((price * 1.08) / area_num, 2),
                'total_installment_price': round(price * 1.08, 2),
                'list_price': price,
                'garage_yes_no': True,
                'garden_yes_no': True,
                'garden_area': 45.0,
            })

        # 3 Demo Sale Orders -> Confirmed -> real.estate.contract (in SAR via SAR pricelist, never touching EGP!)
        SaleOrder = self.env['sale.order'].sudo()
        Contract = self.env['real.estate.contract'].sudo()
        demo_contracts_spec = [
            ('STM-DEMO-SO-01', buyer_1, unit_tmpls['STM-RDY-Y201'], 550000.0, 'delivered', '2026-11-10', '2026-11-10', u_pm.id),
            ('STM-DEMO-SO-02', buyer_2, unit_tmpls['STM-RDY-Y202'], 580000.0, 'ready', '2026-12-01', False, False),
            ('STM-DEMO-SO-03', buyer_3, unit_tmpls['STM-OFF-A101'], 400000.0, 'pending', '2027-06-30', False, False),
        ]
        for origin_key, buyer, tmpl, price, h_status, exp_dt, act_dt, app_uid in demo_contracts_spec:
            so = SaleOrder.search([('origin', '=', origin_key)], limit=1)
            if not so:
                so = SaleOrder.create({
                    'partner_id': buyer.id,
                    'company_id': company.id,
                    'pricelist_id': sar_pricelist.id,
                    'origin': origin_key,
                    'order_line': [(0, 0, {
                        'product_id': tmpl.product_variant_id.id,
                        'name': tmpl.name,
                        'product_uom_qty': 1.0,
                        'price_unit': price,
                    })],
                })
            if so.state in ('draft', 'sent'):
                so.action_confirm()
            contract = Contract.search([('sale_order_id', '=', so.id)], limit=1)
            if contract:
                contract.write({
                    'stm_handover_status': h_status,
                    'stm_expected_handover_date': exp_dt,
                    'stm_actual_handover_date': act_dt,
                    'stm_handover_approved_by': app_uid,
                })

        # 2 Simulated Online Bookings
        Booking = self.env['construction.online.booking'].sudo()
        bk1 = Booking.search([('name', '=', 'WEB-BK/2026/001')], limit=1)
        y203_prod = unit_tmpls['STM-RDY-Y203'].product_variant_id
        if not bk1:
            bk1 = Booking.create({
                'name': 'WEB-BK/2026/001',
                'source_channel': 'website',
                'sync_status': 'synced_sim',
                'partner_id': buyer_4.id,
                'customer_phone': buyer_4.phone,
                'product_id': y203_prod.id,
                'company_id': company.id,
                'currency_id': sar.id,
                'deposit_amount': 50000.0,
                'state': 'incoming',
                'sync_log': '[2026-11-24 09:15:00] [محاكاة] تم استلام طلب حجز إلكتروني للوحدة Y203 مع عربون 50,000 ر.س وبانتظار مراجعة المبيعات/مدير المشروع.',
                'notes': 'طلب حجز وارد من الموقع الإلكتروني — جاهز للاعتماد الحي وتحويله لأمر بيع.',
            })

        bk2 = Booking.search([('name', '=', 'WEB-BK/2026/002')], limit=1)
        y204_prod = unit_tmpls['STM-RDY-Y204'].product_variant_id
        if not bk2:
            bk2 = Booking.create({
                'name': 'WEB-BK/2026/002',
                'source_channel': 'portal',
                'sync_status': 'synced_sim',
                'partner_id': buyer_1.id,
                'customer_phone': buyer_1.phone,
                'product_id': y204_prod.id,
                'company_id': company.id,
                'currency_id': sar.id,
                'deposit_amount': 60000.0,
                'state': 'incoming',
                'sync_log': '[2026-11-23 14:20:00] [محاكاة] تم استلام طلب حجز من بوابة الحجز للوحدة Y204 بعربون 60,000 ر.س.',
            })
        if bk2.state in ('incoming', 'under_review') and not bk2.sale_order_id:
            bk2.action_approve_create_sale()

        # ------------------------------------------------------------------
        # BONUS LIVE-DEMO DRAFT BOQ (BOQ/2026/0004 — فيلا نموذجية — عرض حي للاعتماد)
        # ------------------------------------------------------------------
        boq4 = Boq.search([('name', '=', 'BOQ/2026/0004')], limit=1)
        if not boq4:
            boq4 = Boq.create({
                'name': 'BOQ/2026/0004',
                'project_name': 'فيلا نموذجية — عرض حي للاعتماد',
                'project_type': 'contracting',
                'location': 'جدة — أبحر الشمالية',
                'company_id': company.id,
                'currency_id': sar.id,
                'state': 'draft',
                'date_start_planned': '2026-12-01',
                'date_end_planned': '2027-06-30',
                'date_end_expected': '2027-06-30',
                'land_area': 450.0,
                'building_area': 280.0,
                'total_built_area': 640.0,
                'floors_count': 2,
                'residential_units_count': 1,
                'parking_slots_count': 2,
                'electricity_meters_count': 2,
                'owner_id': p_owner.id,
                'consultant_id': p_consultant.id,
                'project_manager_id': emp_pm.id,
                'project_engineer_id': emp_eng.id,
                'supervisor_id': emp_sup.id,
                'technicians_count': 4,
                'workers_count': 12,
                'equipment_summary': 'خلاطة خرسانة موقعية، هزاز خرسانة، سقالات واجهات.',
                'notes': '<p>مقايسة مسودة مخصصة للعرض الحي — اضغط «اعتماد وإنشاء المشروع» لتحويلها فوراً إلى مشروع ومهام ومراحل.</p>',
                'line_ids': [
                    (0, 0, {'sequence': 10, 'included': True, 'scope_category': 'excavation', 'name': 'أعمال الحفر والردم', 'uom_name': 'م³', 'planned_qty': 400, 'unit_price': 65.0, 'subtasks_count': 1}),
                    (0, 0, {'sequence': 20, 'included': True, 'scope_category': 'structure', 'name': 'أعمال العظم والخرسانة', 'uom_name': 'م²', 'planned_qty': 640, 'unit_price': 230.0, 'subtasks_count': 1}),
                    (0, 0, {'sequence': 30, 'included': True, 'scope_category': 'masonry', 'name': 'أعمال المباني واللياسة', 'uom_name': 'م²', 'planned_qty': 900, 'unit_price': 55.0, 'subtasks_count': 1}),
                    (0, 0, {'sequence': 40, 'included': True, 'scope_category': 'electrical', 'name': 'الأعمال الكهربائية والميكانيكية', 'uom_name': 'مقطوعة', 'planned_qty': 1, 'unit_price': 125000.0, 'subtasks_count': 1}),
                    (0, 0, {'sequence': 50, 'included': True, 'scope_category': 'facades', 'name': 'واجهات الحجر والبورسلان', 'uom_name': 'م²', 'planned_qty': 1500, 'unit_price': 75.0, 'subtasks_count': 3}),
                    (0, 0, {'sequence': 60, 'included': True, 'scope_category': 'painting', 'name': 'التشطيبات النهائية والدهان', 'uom_name': 'م²', 'planned_qty': 800, 'unit_price': 35.0, 'subtasks_count': 1}),
                ],
            })

        # ------------------------------------------------------------------
        # KPI & Liquidity Config (triggers AI Alert #3 with 470,000 SAR deficit)
        # ------------------------------------------------------------------
        KpiConfig = self.env['construction.kpi.config'].sudo()
        cfg = KpiConfig.search([], order='id asc', limit=1)
        cfg_vals = {
            'name': 'إعدادات لوحة الإدارة والسيولة',
            'company_id': company.id,
            'currency_id': sar.id,
            'materials_planned_cost': 1450000.0,
            'materials_consumed_cost': 1180000.0,
            'materials_waste_cost': 42000.0,
            'cash_inflow_expected': 1650000.0,
            'cash_outflow_expected': 2120000.0,
            'overdue_installments_amount': 340000.0,
            'escrow_balance': 1250000.0,
            'saudization_rate': 34.5,
            'ai_liquidity_recommendation': 'تسريع تحصيل أقساط الوحدات الجاهزة (340,000 ر.س متأخرة)، إيداع شيكات PDC المستحقة هذا الأسبوع، وإعادة جدولة صرف مستخلصين غير حرجين لتغطية العجز النقدي (470,000 ر.س) خلال 60 يوماً.',
        }
        if cfg:
            cfg.write(cfg_vals)
        else:
            cfg = KpiConfig.create(cfg_vals)

        summary_html = (
            '<div dir="rtl" class="alert alert-success mb-0">'
            '<h5 class="mb-2">تم تحميل بيانات الديمو المتكاملة بنجاح (بدون تكرار)</h5>'
            '<ul class="mb-0">'
            '<li><strong>المقايسات والمشاريع (4):</strong> '
            'BOQ/2026/0001 (مقاولات إشراقات الحجاز + عقد البلاط .docx) | '
            'BOQ/2026/0002 (بيع على الخارطة — إنذار 70%/90% وتأخير 12 يوم) | '
            'BOQ/2026/0003 (كمباوند الياسمين الجاهز) | '
            'BOQ/2026/0004 (مسودة جاهزة للاعتماد الحي)</li>'
            '<li><strong>المستخلصات (2):</strong> CERT/V/2026/001 (جاري رقم / 12 — نموذج العظم، جاهز لإنشاء الفاتورة) + CERT/C/2026/001 (مستخلص عميل مرتبط بمسودة فاتورة)</li>'
            '<li><strong>طلبات المواد (3):</strong> SRQ/2026/0001 (نقل مخزني) | SRQ/2026/0002 (صرف استهلاك) | SRQ/2026/0003 (بانتظار الاعتماد)</li>'
            '<li><strong>العقارات (12 وحدة جديدة + 3 عقود SAR + حجزين):</strong> مع الحفاظ التام على عقود NEW CAIRO / LA VISTA بعملة EGP وشيكات sh_pdc</li>'
            '<li><strong>المستخدمون الـ 3 (كلمة المرور 1):</strong> site_engineer | project_manager | sales_finance</li>'
            '</ul>'
            '</div>'
        )
        self.last_result_html = summary_html
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'تم تحميل بيانات الديمو بنجاح',
                'message': 'تم تجهيز القصص الثلاث، 12 وحدة، المستخلصات، الحجوزات، والمستخدمين الثلاثة بدون تكرار.',
                'type': 'success',
                'sticky': False,
            },
        }

    # ------------------------------------------------------------------
    # One-Click Rehearsal Reset («تجهيز مسرح العرض للبروفة»)
    # ------------------------------------------------------------------
    def action_reset_rehearsal_triggers(self):
        self.ensure_one()
        Boq = self.env['construction.boq'].sudo()
        Task = self.env['project.task'].sudo()
        SiteReq = self.env['construction.site.request'].sudo()
        Booking = self.env['construction.online.booking'].sudo()
        Cert = self.env['construction.certificate'].sudo()
        Contract = self.env['real.estate.contract'].sudo()

        # 1. Reset BOQ/2026/0004 back to Draft (unlink generated project & tasks only for BOQ/2026/0004)
        boq4 = Boq.search([('name', '=', 'BOQ/2026/0004')], limit=1)
        if boq4:
            proj = boq4.project_id
            if proj:
                tasks = Task.search([('project_id', '=', proj.id)])
                boq4.line_ids.write({'task_id': False})
                if tasks:
                    # Unlink subtasks before parents
                    subtasks = tasks.filtered('parent_id')
                    if subtasks:
                        subtasks.unlink()
                    remaining = Task.search([('project_id', '=', proj.id)])
                    if remaining:
                        remaining.unlink()
                boq4.write({'project_id': False, 'state': 'draft'})
                proj.unlink()
            elif boq4.state != 'draft':
                boq4.write({'state': 'draft'})

        # 2. Reset SRQ/2026/0003 back to submitted (PM approval/rejection live trigger)
        srq3 = SiteReq.search([('name', '=', 'SRQ/2026/0003')], limit=1)
        if srq3:
            if srq3.purchase_order_id:
                po = srq3.purchase_order_id
                srq3.write({'purchase_order_id': False})
                if po.state not in ('done', 'cancel'):
                    po.button_cancel()
                if po.state == 'cancel':
                    po.unlink()
            if srq3.picking_id:
                pick = srq3.picking_id
                srq3.write({'picking_id': False})
                if pick.state != 'done':
                    pick.action_cancel()
                    pick.unlink()
            srq3.write({
                'state': 'submitted',
                'approved_by_id': False,
                'rejection_reason': False,
            })

        # 3. Reset WEB-BK/2026/001 back to incoming (Online Booking approval live trigger)
        bk1 = Booking.search([('name', '=', 'WEB-BK/2026/001')], limit=1)
        if bk1:
            if bk1.sale_order_id:
                so = bk1.sale_order_id
                bk1.write({'sale_order_id': False})
                linked_contracts = Contract.search([('sale_order_id', '=', so.id)])
                if linked_contracts:
                    linked_contracts.unlink()
                if so.state != 'cancel':
                    so._action_cancel()
                so.unlink()
            if bk1.product_id:
                bk1.product_id.product_tmpl_id.write({'stm_unit_availability': 'available'})
            bk1.write({
                'state': 'incoming',
                'rejection_reason': False,
                'sync_status': 'synced_sim',
                'sync_log': '[2026-11-24 09:15:00] [محاكاة] تم استلام طلب حجز إلكتروني للوحدة Y203 مع عربون 50,000 ر.س وبانتظار مراجعة المبيعات/مدير المشروع.',
            })

        # 4. Reset CERT/V/2026/001 (جاري رقم / 12) back to pm_approved (ready to create draft Vendor Bill)
        cert_v = Cert.search([('name', '=', 'CERT/V/2026/001')], limit=1)
        if cert_v:
            if cert_v.move_id and cert_v.move_id.state == 'draft':
                mv = cert_v.move_id
                cert_v.write({'move_id': False})
                mv.unlink()
            u_eng = self.env['res.users'].sudo().search([('login', '=', 'site_engineer')], limit=1)
            u_pm = self.env['res.users'].sudo().search([('login', '=', 'project_manager')], limit=1)
            vals = {
                'state': 'pm_approved',
                'accounting_approved_by_id': False,
                'rejection_reason': False,
            }
            if u_eng:
                vals['site_engineer_id'] = u_eng.id
            if u_pm:
                vals['pm_approved_by_id'] = u_pm.id
            cert_v.write(vals)

        # 5. Reset Ready unit contract STM-DEMO-SO-02 (Y202) back to ready for live handover approval
        so2 = self.env['sale.order'].sudo().search([('origin', '=', 'STM-DEMO-SO-02')], limit=1)
        if so2:
            c2 = Contract.search([('sale_order_id', '=', so2.id)], limit=1)
            if c2:
                c2.write({
                    'stm_handover_status': 'ready',
                    'stm_actual_handover_date': False,
                    'stm_handover_approved_by': False,
                })
                if c2.product_id:
                    c2.product_id.product_tmpl_id.write({
                        'stm_handover_readiness': 'ready',
                        'stm_unit_availability': 'sold',
                    })

        self.last_result_html = (
            '<div dir="rtl" class="alert alert-info mb-0">'
            '<strong>تم تجهيز مسرح العرض للبروفة بنجاح:</strong> '
            'BOQ/2026/0004 (مسودة) • SRQ/2026/0003 (بانتظار الاعتماد) • '
            'WEB-BK/2026/001 (حجز وارد) • جاري رقم / 12 (جاهز لإنشاء مسودة فاتورة مورد) • '
            'عقد Y202 (جاهز لاعتماد التسليم). عقود NEW CAIRO / LA VISTA وشيكات sh_pdc لم تُمس إطلاقاً.'
            '</div>'
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'تم تجهيز مسرح العرض للبروفة',
                'message': 'تمت إعادة ضبط نقاط التفاعل الحية الأربعة مع بقاء بيانات القاعدة وعقود NEW CAIRO سليمة 100%.',
                'type': 'success',
                'sticky': False,
            },
        }
