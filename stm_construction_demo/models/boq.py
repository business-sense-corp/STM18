# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

STANDARD_SCOPE_ITEMS = [
    ('excavation', 'حفر وردم', 'م³'),
    ('structure', 'عظم', 'م²'),
    ('masonry', 'مباني', 'م²'),
    ('plastering', 'لياسة', 'م²'),
    ('insulation', 'عزل', 'م²'),
    ('electrical', 'كهرباء', 'مقطوعة'),
    ('hvac', 'تكييف', 'مقطوعة'),
    ('plumbing', 'سباكة', 'مقطوعة'),
    ('safety', 'أمن وسلامة', 'مقطوعة'),
    ('tiling', 'بلاط', 'م²'),
    ('irrigation', 'ري', 'مقطوعة'),
    ('painting', 'دهان', 'م²'),
    ('windows', 'شبابيك', 'م²'),
    ('doors', 'أبواب', 'عدد'),
    ('ceilings', 'أسقف', 'م²'),
    ('elevators', 'مصاعد', 'عدد'),
    ('epoxy', 'إيبوكسي', 'م²'),
    ('agriculture', 'زراعة', 'م²'),
    ('landscape', 'لاندسكيب (مناطق خضراء - مسبح - جلسات - ممرات رياضة)', 'م²'),
    ('facades', 'واجهات', 'م²'),
    ('other', 'أخرى', 'مقطوعة'),
]

SCOPE_SELECTION = [(k, lbl) for k, lbl, _uom in STANDARD_SCOPE_ITEMS]
SCOPE_UOM_MAP = {k: uom for k, _lbl, uom in STANDARD_SCOPE_ITEMS}
SCOPE_LABEL_MAP = {k: lbl for k, lbl, _uom in STANDARD_SCOPE_ITEMS}

STANDARD_DOCUMENTS = [
    ('official', 'الرخصة', True),
    ('official', 'الصك', True),
    ('official', 'القرار المساحي', True),
    ('official', 'المخططات المعتمدة (باركود الأمانة)', True),
    ('official', 'المخططات التنفيذية الإنشائية', True),
    ('official', 'المخططات التنفيذية المعمارية', True),
    ('official', 'المخططات التنفيذية الميكانيكية', True),
    ('official', 'المخططات التنفيذية الكهربائية', True),
    ('official', 'مخططات الأمن والسلامة', True),
    ('official', 'تقرير التربة', True),
    ('official', 'جداول الكميات', True),
    ('official', 'الجدول الزمني', True),
    ('subcontract', 'عقود مقاولي الباطن', True),
    ('reports', 'محضر استلام الموقع', True),
    ('reports', 'تقارير الإشراف', True),
    ('reports', 'تقارير التأمين', False),
    ('reports', 'اختبارات الدمك', True),
    ('reports', 'وصولات استلام الخرسانة', True),
    ('reports', 'اختبارات الخرسانة', True),
    ('reports', 'اختبارات العزل', True),
    ('reports', 'تقارير الدفاع المدني', True),
    ('reports', 'التقارير الدورية (أسبوعية / شهرية)', True),
    ('reports', 'تقارير أخرى', False),
    ('admin', 'فواتير المواد الموردة', True),
]


class ConstructionBoq(models.Model):
    _name = 'construction.boq'
    _description = 'المقايسة وبطاقة المشروع (BOQ)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    @api.model
    def _default_sar_currency(self):
        sar = self.env['res.currency'].search(
            [('name', '=', 'SAR'), ('active', '=', True)], limit=1
        )
        return sar or self.env.company.currency_id

    name = fields.Char(
        string='رقم المقايسة',
        required=True,
        copy=False,
        readonly=True,
        default='جديد',
    )
    project_name = fields.Char(
        string='اسم المشروع',
        required=True,
        tracking=True,
    )
    project_type = fields.Selection(
        [
            ('off_plan', 'بيع على الخارطة'),
            ('ready', 'وحدات جاهزة'),
            ('contracting', 'مقاولات للغير'),
        ],
        string='نوع المشروع',
        default='contracting',
        required=True,
        tracking=True,
    )
    location = fields.Char(string='موقع المشروع', tracking=True)
    company_id = fields.Many2one(
        'res.company',
        string='الشركة',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='العملة',
        default=_default_sar_currency,
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ('draft', 'مسودة'),
            ('confirmed', 'معتمد'),
            ('in_progress', 'قيد التنفيذ'),
            ('done', 'مكتمل'),
        ],
        string='الحالة',
        default='draft',
        required=True,
        tracking=True,
    )

    # Dates & Delay
    date_start_planned = fields.Date(string='بداية المشروع (المخطط)', tracking=True)
    date_start_actual = fields.Date(string='بداية المشروع (الفعلي)', tracking=True)
    date_end_planned = fields.Date(string='نهاية المشروع (المخطط)', tracking=True)
    date_end_expected = fields.Date(string='نهاية المشروع (المتوقع)', tracking=True)
    delay_days = fields.Integer(
        string='أيام التأخير',
        compute='_compute_delay_days',
        store=True,
        readonly=False,
        tracking=True,
    )
    delay_reason = fields.Text(string='سبب التأخير', tracking=True)
    notes = fields.Html(string='الملاحظات والتعليقات')

    # Tab 1: 8 Exact Excel Project Specs (بيانات ومستندات رسمية.xlsx)
    land_area = fields.Float(string='مساحة قطعة الأرض (م²)')
    building_area = fields.Float(string='مساحة المبنى (م²)')
    total_built_area = fields.Float(string='إجمالي المسطحات المبنية (م²)')
    floors_count = fields.Integer(string='عدد الأدوار')
    residential_units_count = fields.Integer(string='عدد الوحدات السكنية')
    commercial_shops_count = fields.Integer(string='عدد المحلات التجارية')
    parking_slots_count = fields.Integer(string='عدد مواقف السيارات')
    electricity_meters_count = fields.Integer(string='عدد عدادات الكهرباء')

    # Tab 2: BOQ Lines & Totals
    line_ids = fields.One2many(
        'construction.boq.line',
        'boq_id',
        string='بنود المقايسة والتكاليف',
    )
    total_planned = fields.Monetary(
        string='إجمالي الميزانية المخططة',
        currency_field='currency_id',
        compute='_compute_boq_totals',
        store=True,
    )
    total_actual = fields.Monetary(
        string='إجمالي المنصرف الفعلي',
        currency_field='currency_id',
        compute='_compute_boq_totals',
        store=True,
    )
    total_committed = fields.Monetary(
        string='إجمالي الالتزامات',
        currency_field='currency_id',
        compute='_compute_boq_totals',
        store=True,
    )
    total_etc = fields.Monetary(
        string='تكلفة الإكمال المتبقية (ETC)',
        currency_field='currency_id',
        compute='_compute_boq_totals',
        store=True,
    )
    total_eac = fields.Monetary(
        string='التكلفة النهائية المتوقعة (EAC)',
        currency_field='currency_id',
        compute='_compute_boq_totals',
        store=True,
    )
    budget_variance = fields.Monetary(
        string='الانحراف عن الميزانية',
        currency_field='currency_id',
        compute='_compute_boq_totals',
        store=True,
        help='القيمة الموجبة تعني تجاوزاً متوقعاً في التكلفة عن المخطط.',
    )
    progress_percent = fields.Float(
        string='نسبة الإنجاز الكلية (%)',
        compute='_compute_boq_totals',
        store=True,
        digits=(5, 2),
    )
    cost_burn_percent = fields.Float(
        string='نسبة الصرف من الميزانية (%)',
        compute='_compute_boq_totals',
        store=True,
        digits=(5, 2),
    )
    is_over_budget = fields.Boolean(
        string='تجاوز الميزانية',
        compute='_compute_boq_totals',
        store=True,
    )
    is_early_cost_alert = fields.Boolean(
        string='تنبيه تكلفة مبكر (70%/90%)',
        compute='_compute_boq_totals',
        store=True,
    )

    # Tab 3: 5 Parties + Vendors + Crew + Equipment
    owner_id = fields.Many2one('res.partner', string='المالك')
    consultant_id = fields.Many2one('res.partner', string='الاستشاري')
    designer_id = fields.Many2one('res.partner', string='المكتب المصمم')
    insurance_company_id = fields.Many2one('res.partner', string='شركة التأمين')
    official_authority_id = fields.Many2one('res.partner', string='أطراف رسمية')
    vendor_ids = fields.Many2many(
        'res.partner',
        'construction_boq_vendor_rel',
        'boq_id',
        'partner_id',
        string='الموردون ومقاولو الباطن',
    )

    project_manager_id = fields.Many2one('hr.employee', string='مدير المشروع')
    project_engineer_id = fields.Many2one('hr.employee', string='مهندس المشروع')
    supervisor_id = fields.Many2one('hr.employee', string='مشرف المشروع')
    technicians_count = fields.Integer(string='عدد الفنيين')
    workers_count = fields.Integer(string='عدد العمال')
    equipment_summary = fields.Text(string='المعدات والآليات بالموقع')

    # Tab 4: Official Documents Checklist
    document_line_ids = fields.One2many(
        'construction.boq.document',
        'boq_id',
        string='المستندات والمرفقات الرسمية',
    )
    docs_total_count = fields.Integer(
        string='إجمالي المستندات',
        compute='_compute_document_stats',
    )
    docs_uploaded_count = fields.Integer(
        string='المستندات المرفقة/المعتمدة',
        compute='_compute_document_stats',
    )
    docs_pending_count = fields.Integer(
        string='المستندات المطلوبة',
        compute='_compute_document_stats',
    )

    # Links & Smart Button Counters
    project_id = fields.Many2one(
        'project.project',
        string='المشروع التنفيذي',
        copy=False,
        readonly=True,
        tracking=True,
    )
    task_count = fields.Integer(
        string='عدد المهام',
        compute='_compute_link_counts',
    )
    site_request_count = fields.Integer(
        string='طلبات المواد',
        compute='_compute_link_counts',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'جديد':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('construction.boq')
                    or 'BOQ/2026/0001'
                )
        return super().create(vals_list)

    @api.depends('date_end_planned', 'date_end_expected')
    def _compute_delay_days(self):
        for rec in self:
            if rec.date_end_planned and rec.date_end_expected:
                delta = (rec.date_end_expected - rec.date_end_planned).days
                rec.delay_days = max(0, delta)
            elif not rec.delay_days:
                rec.delay_days = 0

    @api.depends(
        'line_ids.included',
        'line_ids.planned_amount',
        'line_ids.actual_amount',
        'line_ids.committed_amount',
        'line_ids.etc_amount',
        'line_ids.eac_amount',
        'line_ids.progress_percent',
    )
    def _compute_boq_totals(self):
        for rec in self:
            inc = rec.line_ids.filtered('included')
            rec.total_planned = sum(inc.mapped('planned_amount'))
            rec.total_actual = sum(inc.mapped('actual_amount'))
            rec.total_committed = sum(inc.mapped('committed_amount'))
            rec.total_etc = sum(inc.mapped('etc_amount'))
            rec.total_eac = sum(inc.mapped('eac_amount'))
            rec.budget_variance = rec.total_eac - rec.total_planned

            if rec.total_planned > 0:
                weighted = sum(l.planned_amount * l.progress_percent for l in inc)
                rec.progress_percent = weighted / rec.total_planned
                rec.cost_burn_percent = (rec.total_actual / rec.total_planned) * 100.0
            elif inc:
                rec.progress_percent = sum(inc.mapped('progress_percent')) / len(inc)
                rec.cost_burn_percent = 0.0
            else:
                rec.progress_percent = 0.0
                rec.cost_burn_percent = 0.0

            rec.is_over_budget = (
                rec.total_actual > rec.total_planned
                or rec.total_eac > rec.total_planned
            ) if rec.total_planned > 0 else False
            rec.is_early_cost_alert = (
                rec.total_planned > 0
                and rec.progress_percent <= 75.0
                and rec.cost_burn_percent >= 85.0
            )

    @api.depends('document_line_ids.status')
    def _compute_document_stats(self):
        for rec in self:
            docs = rec.document_line_ids
            rec.docs_total_count = len(docs)
            rec.docs_uploaded_count = len(
                docs.filtered(lambda d: d.status in ('uploaded', 'approved'))
            )
            rec.docs_pending_count = len(
                docs.filtered(lambda d: d.status == 'pending')
            )

    def _compute_link_counts(self):
        Task = self.env['project.task']
        SiteRequest = self.env['construction.site.request']
        for rec in self:
            if rec.project_id:
                rec.task_count = Task.search_count([('project_id', '=', rec.project_id.id)])
                rec.site_request_count = SiteRequest.search_count(
                    ['|', ('boq_id', '=', rec.id), ('project_id', '=', rec.project_id.id)]
                )
            else:
                rec.task_count = 0
                rec.site_request_count = SiteRequest.search_count([('boq_id', '=', rec.id)])

    def action_populate_standard_scope(self):
        for rec in self:
            existing_cats = set(rec.line_ids.mapped('scope_category'))
            vals_to_add = []
            seq = (max(rec.line_ids.mapped('sequence') or [0])) + 10
            for key, label, uom in STANDARD_SCOPE_ITEMS:
                if key not in existing_cats:
                    vals_to_add.append(
                        (
                            0,
                            0,
                            {
                                'sequence': seq,
                                'included': True,
                                'scope_category': key,
                                'name': label,
                                'uom_name': uom,
                            },
                        )
                    )
                    seq += 10
            if vals_to_add:
                rec.write({'line_ids': vals_to_add})
        return True

    def action_populate_standard_documents(self):
        for rec in self:
            existing_names = set(rec.document_line_ids.mapped('name'))
            vals_to_add = []
            for cat, doc_name, is_req in STANDARD_DOCUMENTS:
                if doc_name not in existing_names:
                    vals_to_add.append(
                        (
                            0,
                            0,
                            {
                                'category': cat,
                                'name': doc_name,
                                'required': is_req,
                                'status': 'pending',
                            },
                        )
                    )
            if vals_to_add:
                rec.write({'document_line_ids': vals_to_add})
        return True

    def _ensure_project_stages(self, project):
        Stage = self.env['project.task.type']
        stage_specs = [
            ('مخطط', 10, False),
            ('قيد التنفيذ', 20, False),
            ('مراجعة استشاري', 30, False),
            ('متأخر', 40, False),
            ('مكتمل', 50, True),
        ]
        stage_map = {}
        for s_name, seq, fold in stage_specs:
            stage = Stage.search([('name', '=', s_name)], limit=1)
            if not stage:
                stage = Stage.create(
                    {
                        'name': s_name,
                        'sequence': seq,
                        'fold': fold,
                        'project_ids': [(4, project.id)],
                    }
                )
            elif project.id not in stage.project_ids.ids:
                stage.write({'project_ids': [(4, project.id)]})
            stage_map[s_name] = stage
        return stage_map

    def action_confirm_create_project(self):
        Project = self.env['project.project']
        Task = self.env['project.task']
        for rec in self:
            included_lines = rec.line_ids.filtered('included')
            if not included_lines:
                raise UserError(
                    'يرجى إضافة بند واحد مشمول على الأقل في المقايسة قبل اعتماد المشروع.'
                )

            if not rec.project_id:
                project = Project.create(
                    {
                        'name': rec.project_name,
                        'partner_id': rec.owner_id.id or False,
                        'company_id': rec.company_id.id,
                        'date_start': rec.date_start_planned or False,
                        'date': rec.date_end_planned or False,
                        'allow_milestones': True,
                        'stm_boq_id': rec.id,
                        'stm_project_type': rec.project_type,
                        'stm_delay_days': rec.delay_days,
                        'stm_delay_reason': rec.delay_reason,
                        'stm_equipment_summary': rec.equipment_summary,
                    }
                )
                rec.project_id = project.id
            else:
                project = rec.project_id
                project.write(
                    {
                        'stm_boq_id': rec.id,
                        'stm_project_type': rec.project_type,
                        'stm_delay_days': rec.delay_days,
                        'stm_delay_reason': rec.delay_reason,
                        'stm_equipment_summary': rec.equipment_summary,
                    }
                )

            stage_map = rec._ensure_project_stages(project)
            created_tasks = 0
            created_subtasks = 0

            for line in included_lines:
                if line.task_id:
                    continue
                if line.progress_percent >= 100.0:
                    stage = stage_map['مكتمل']
                elif line.progress_percent > 0.0:
                    stage = stage_map['قيد التنفيذ']
                else:
                    stage = stage_map['مخطط']

                executed_qty = (
                    line.planned_qty * (line.progress_percent / 100.0)
                    if line.planned_qty
                    else 0.0
                )
                task = Task.create(
                    {
                        'name': line.name,
                        'project_id': project.id,
                        'stage_id': stage.id,
                        'partner_id': rec.owner_id.id or False,
                        'stm_boq_line_id': line.id,
                        'stm_planned_qty': line.planned_qty,
                        'stm_executed_qty': executed_qty,
                        'stm_progress_percent': line.progress_percent,
                    }
                )
                line.task_id = task.id
                created_tasks += 1

                split_count = line.subtasks_count
                if split_count <= 1 and line.scope_category in ('excavation', 'facades', 'tiling') and line.planned_qty >= 1000:
                    split_count = 3

                if split_count > 1:
                    if split_count == 3:
                        ratios = [0.20, 0.30, 0.50]
                    else:
                        ratios = [1.0 / split_count] * split_count
                    for idx, ratio in enumerate(ratios, start=1):
                        sub_qty = round(line.planned_qty * ratio, 2)
                        Task.create(
                            {
                                'name': f"{line.name} — المرحلة {idx}",
                                'project_id': project.id,
                                'parent_id': task.id,
                                'stage_id': stage.id,
                                'partner_id': rec.owner_id.id or False,
                                'stm_planned_qty': sub_qty,
                                'stm_executed_qty': round(sub_qty * (line.progress_percent / 100.0), 2),
                                'stm_progress_percent': line.progress_percent,
                            }
                        )
                        created_subtasks += 1

            if rec.state == 'draft':
                rec.state = 'confirmed'

            rec.message_post(
                body=(
                    f"تم اعتماد المقايسة وربطها بالمشروع <b>{project.name}</b> "
                    f"(إنشاء {created_tasks} مهمة رئيسية و {created_subtasks} مهمة فرعية)."
                )
            )
        return True

    def action_set_in_progress(self):
        self.write({'state': 'in_progress'})
        return True

    def action_set_done(self):
        self.write({'state': 'done'})
        return True

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_print_boq_pdf(self):
        self.ensure_one()
        return self.env.ref('stm_construction_demo.action_report_construction_boq').report_action(self)

    def action_view_project(self):
        self.ensure_one()
        if not self.project_id:
            raise UserError('لم يتم إنشاء مشروع تنفيذي لهذه المقايسة بعد.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'المشروع التنفيذي',
            'res_model': 'project.project',
            'view_mode': 'form',
            'res_id': self.project_id.id,
        }

    def action_view_tasks(self):
        self.ensure_one()
        if not self.project_id:
            raise UserError('لم يتم إنشاء مشروع تنفيذي لهذه المقايسة بعد.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'المهام والمراحل التنفيذية',
            'res_model': 'project.task',
            'view_mode': 'list,kanban,form',
            'domain': [('project_id', '=', self.project_id.id)],
            'context': {'default_project_id': self.project_id.id},
        }

    def action_view_site_requests(self):
        self.ensure_one()
        domain = ['|', ('boq_id', '=', self.id), ('project_id', '=', self.project_id.id)] if self.project_id else [('boq_id', '=', self.id)]
        return {
            'type': 'ir.actions.act_window',
            'name': 'طلبات مواد الموقع',
            'res_model': 'construction.site.request',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'default_boq_id': self.id,
                'default_project_id': self.project_id.id if self.project_id else False,
            },
        }


class ConstructionBoqLine(models.Model):
    _name = 'construction.boq.line'
    _description = 'بند المقايسة'
    _order = 'sequence, id'

    boq_id = fields.Many2one(
        'construction.boq',
        string='المقايسة',
        required=True,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='boq_id.currency_id',
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(string='م', default=10)
    included = fields.Boolean(string='شامل', default=True)
    is_variation_order = fields.Boolean(string='أمر تغييري', default=False)
    scope_category = fields.Selection(
        SCOPE_SELECTION,
        string='التصنيف القياسي',
        default='other',
    )
    name = fields.Char(string='وصف البند', required=True)
    uom_name = fields.Char(string='الوحدة', default='م²')
    planned_qty = fields.Float(string='الكمية المخططة', default=1.0)
    unit_price = fields.Monetary(string='سعر الوحدة', currency_field='currency_id')
    planned_amount = fields.Monetary(
        string='الإجمالي المخطط',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
    )
    actual_amount = fields.Monetary(string='المنصرف الفعلي', currency_field='currency_id')
    committed_amount = fields.Monetary(string='الالتزامات', currency_field='currency_id')
    etc_amount = fields.Monetary(string='تكلفة الإكمال (ETC)', currency_field='currency_id')
    eac_amount = fields.Monetary(
        string='التكلفة النهائية (EAC)',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
    )
    variance_amount = fields.Monetary(
        string='الانحراف',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
    )
    progress_percent = fields.Float(string='الإنجاز (%)', digits=(5, 2))
    subtasks_count = fields.Integer(string='مراحل فرعية', default=0)
    task_id = fields.Many2one(
        'project.task',
        string='المهمة المرتبطة',
        readonly=True,
        copy=False,
    )

    @api.depends('planned_qty', 'unit_price', 'actual_amount', 'etc_amount')
    def _compute_amounts(self):
        for line in self:
            planned = (line.planned_qty or 0.0) * (line.unit_price or 0.0)
            eac = (line.actual_amount or 0.0) + (line.etc_amount or 0.0)
            line.planned_amount = planned
            line.eac_amount = eac
            line.variance_amount = eac - planned

    @api.onchange('scope_category')
    def _onchange_scope_category(self):
        if self.scope_category:
            if not self.name:
                self.name = SCOPE_LABEL_MAP.get(self.scope_category, '')
            if not self.uom_name or self.uom_name == 'م²':
                self.uom_name = SCOPE_UOM_MAP.get(self.scope_category, 'م²')


class ConstructionBoqDocument(models.Model):
    _name = 'construction.boq.document'
    _description = 'مستند ومرفق المشروع الرسمي'
    _order = 'category, id'

    boq_id = fields.Many2one(
        'construction.boq',
        string='المقايسة',
        required=True,
        ondelete='cascade',
    )
    category = fields.Selection(
        [
            ('official', 'مستندات المشروع'),
            ('subcontract', 'عقود مقاولي الباطن'),
            ('reports', 'التقارير والاختبارات'),
            ('admin', 'المستندات الإدارية والمالية'),
        ],
        string='التصنيف',
        required=True,
        default='official',
    )
    name = fields.Char(string='اسم المستند', required=True)
    required = fields.Boolean(string='إلزامي', default=True)
    status = fields.Selection(
        [
            ('pending', 'مطلوب'),
            ('uploaded', 'مرفق'),
            ('approved', 'معتمد'),
        ],
        string='الحالة',
        default='pending',
        required=True,
    )
    attachment_file = fields.Binary(string='ملف المرفق', attachment=True)
    attachment_filename = fields.Char(string='اسم الملف')
    notes = fields.Char(string='ملاحظات')

    @api.onchange('attachment_file')
    def _onchange_attachment_file(self):
        if self.attachment_file and self.status == 'pending':
            self.status = 'uploaded'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('attachment_file') and vals.get('status', 'pending') == 'pending':
                vals['status'] = 'uploaded'
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('attachment_file') and 'status' not in vals:
            for rec in self:
                if rec.status == 'pending':
                    vals = dict(vals, status='uploaded')
                    break
        return super().write(vals)
