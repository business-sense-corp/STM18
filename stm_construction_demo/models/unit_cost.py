# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ConstructionUnitCost(models.Model):
    _name = 'construction.unit.cost'
    _description = 'بطاقة تكلفة وربحية البلوك والوحدة'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'is_featured desc, id desc'

    @api.model
    def _default_sar_currency(self):
        sar = self.env['res.currency'].search(
            [('name', '=', 'SAR'), ('active', '=', True)], limit=1
        )
        return sar or self.env.company.currency_id

    name = fields.Char(
        string='اسم البلوك / النموذج',
        required=True,
        default='بلوك إشراقات السكني — 10 وحدات',
        tracking=True,
    )
    project_id = fields.Many2one(
        'project.project',
        string='المشروع الإنشائي',
        tracking=True,
    )
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
    is_featured = fields.Boolean(
        string='عرض رئيسي على لوحة الإدارة',
        default=True,
        tracking=True,
    )

    # Block Inputs
    units_count = fields.Integer(
        string='عدد الوحدات بالبلوك',
        default=10,
        required=True,
        tracking=True,
    )
    block_budget = fields.Monetary(
        string='الميزانية المخططة للبلوك',
        currency_field='currency_id',
        default=3000000.0,
        tracking=True,
    )
    block_actual = fields.Monetary(
        string='المنصرف الفعلي حتى الآن',
        currency_field='currency_id',
        default=1800000.0,
        tracking=True,
    )
    block_etc = fields.Monetary(
        string='تكلفة الإكمال المتبقية (ETC)',
        currency_field='currency_id',
        default=1500000.0,
        tracking=True,
    )

    # Block Computed
    block_eac = fields.Monetary(
        string='التكلفة النهائية المتوقعة للبلوك (EAC)',
        currency_field='currency_id',
        compute='_compute_unit_economics',
        store=True,
    )
    block_variance = fields.Monetary(
        string='انحراف التكلفة المتوقع للبلوك',
        currency_field='currency_id',
        compute='_compute_unit_economics',
        store=True,
    )
    block_variance_pct = fields.Float(
        string='نسبة الانحراف (%)',
        compute='_compute_unit_economics',
        store=True,
        digits=(5, 2),
    )

    # Per-Unit Computed & Sale Inputs
    unit_planned_cost = fields.Monetary(
        string='التكلفة المخططة للوحدة',
        currency_field='currency_id',
        compute='_compute_unit_economics',
        store=True,
    )
    unit_actual_cost = fields.Monetary(
        string='المنصرف الفعلي للوحدة',
        currency_field='currency_id',
        compute='_compute_unit_economics',
        store=True,
    )
    unit_expected_cost = fields.Monetary(
        string='التكلفة المتوقعة للوحدة (EAC)',
        currency_field='currency_id',
        compute='_compute_unit_economics',
        store=True,
    )
    unit_net_sale_price = fields.Monetary(
        string='صافي سعر بيع الوحدة',
        currency_field='currency_id',
        default=400000.0,
        tracking=True,
    )
    unit_cash_collected = fields.Monetary(
        string='المحصّل نقداً للوحدة',
        currency_field='currency_id',
        default=100000.0,
        tracking=True,
    )
    unit_remaining_receivable = fields.Monetary(
        string='المتبقي على العميل للوحدة',
        currency_field='currency_id',
        compute='_compute_unit_economics',
        store=True,
    )
    unit_expected_margin = fields.Monetary(
        string='الهامش المتوقع للوحدة',
        currency_field='currency_id',
        compute='_compute_unit_economics',
        store=True,
    )
    unit_expected_margin_pct = fields.Float(
        string='نسبة الهامش المتوقع (%)',
        compute='_compute_unit_economics',
        store=True,
        digits=(5, 2),
    )
    unit_cash_collected_pct = fields.Float(
        string='نسبة التحصيل النقدي (%)',
        compute='_compute_unit_economics',
        store=True,
        digits=(5, 2),
    )
    accounting_note = fields.Char(
        string='ملاحظة محاسبية',
        default='ملاحظة محاسبية: التحصيل النقدي لا يساوي ربحاً محققاً (الأرقام قبل الضرائب).',
        required=True,
    )
    notes = fields.Text(string='ملاحظات إضافية')

    @api.constrains('units_count')
    def _check_units_count(self):
        for rec in self:
            if rec.units_count <= 0:
                raise ValidationError(_('يجب أن يكون عدد الوحدات بالبلوك أكبر من صفر.'))

    @api.depends(
        'units_count',
        'block_budget',
        'block_actual',
        'block_etc',
        'unit_net_sale_price',
        'unit_cash_collected',
    )
    def _compute_unit_economics(self):
        for rec in self:
            count = rec.units_count if rec.units_count and rec.units_count > 0 else 1
            block_eac = (rec.block_actual or 0.0) + (rec.block_etc or 0.0)
            block_variance = block_eac - (rec.block_budget or 0.0)
            rec.block_eac = block_eac
            rec.block_variance = block_variance
            rec.block_variance_pct = (
                (block_variance / rec.block_budget) * 100.0 if rec.block_budget else 0.0
            )

            rec.unit_planned_cost = (rec.block_budget or 0.0) / count
            rec.unit_actual_cost = (rec.block_actual or 0.0) / count
            unit_expected_cost = block_eac / count
            rec.unit_expected_cost = unit_expected_cost

            sale_price = rec.unit_net_sale_price or 0.0
            collected = rec.unit_cash_collected or 0.0
            rec.unit_remaining_receivable = max(0.0, sale_price - collected)

            margin = sale_price - unit_expected_cost
            rec.unit_expected_margin = margin
            rec.unit_expected_margin_pct = (
                (margin / sale_price) * 100.0 if sale_price else 0.0
            )
            rec.unit_cash_collected_pct = (
                (collected / sale_price) * 100.0 if sale_price else 0.0
            )


class ConstructionKpiConfig(models.Model):
    _name = 'construction.kpi.config'
    _description = 'إعدادات لوحة الإدارة والسيولة'
    _inherit = ['mail.thread']
    _order = 'id asc'

    @api.model
    def _default_sar_currency(self):
        sar = self.env['res.currency'].search(
            [('name', '=', 'SAR'), ('active', '=', True)], limit=1
        )
        return sar or self.env.company.currency_id

    name = fields.Char(
        string='الاسم',
        required=True,
        default='إعدادات لوحة الإدارة والسيولة',
    )
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
    )

    # Materials Control
    materials_planned_cost = fields.Monetary(
        string='تكلفة المواد المخططة',
        currency_field='currency_id',
        default=1200000.0,
        tracking=True,
    )
    materials_consumed_cost = fields.Monetary(
        string='تكلفة المواد المستهلكة فعلياً',
        currency_field='currency_id',
        default=940000.0,
        tracking=True,
    )
    materials_waste_cost = fields.Monetary(
        string='تكلفة هالك المواد',
        currency_field='currency_id',
        default=48000.0,
        tracking=True,
    )
    materials_waste_pct = fields.Float(
        string='نسبة الهالك (%)',
        compute='_compute_materials_waste_pct',
        store=True,
        digits=(5, 2),
    )

    # Liquidity & Cashflow
    cash_inflow_expected = fields.Monetary(
        string='متحصلات متوقعة (60 يوم)',
        currency_field='currency_id',
        default=1450000.0,
        tracking=True,
    )
    cash_outflow_expected = fields.Monetary(
        string='التزامات ومستخلصات متوقعة (60 يوم)',
        currency_field='currency_id',
        default=1980000.0,
        tracking=True,
    )
    cash_deficit_amount = fields.Monetary(
        string='العجز النقدي المتوقع',
        currency_field='currency_id',
        compute='_compute_cash_deficit',
        store=True,
    )
    overdue_installments_amount = fields.Monetary(
        string='الأقساط المتأخرة التحصيل',
        currency_field='currency_id',
        default=320000.0,
        tracking=True,
    )

    # Regulatory Illustrative Scene (Simulated)
    escrow_balance = fields.Monetary(
        string='رصيد حساب الضمان (محاكاة)',
        currency_field='currency_id',
        default=1850000.0,
        tracking=True,
    )
    saudization_rate = fields.Float(
        string='نسبة التوطين % (محاكاة)',
        default=34.5,
        digits=(5, 2),
        tracking=True,
    )
    ai_liquidity_recommendation = fields.Text(
        string='الإجراء المقترح للسيولة (المساعد الذكي)',
        default='تسريع تحصيل أقساط الوحدات الجاهزة (320,000 ر.س متأخرة)، إيداع شيكات PDC المستحقة هذا الأسبوع، وإعادة جدولة صرف مستخلصين غير حرجين لتغطية الفجوة النقدية خلال 60 يوماً.',
    )

    @api.depends('materials_consumed_cost', 'materials_waste_cost')
    def _compute_materials_waste_pct(self):
        for rec in self:
            rec.materials_waste_pct = (
                (rec.materials_waste_cost / rec.materials_consumed_cost) * 100.0
                if rec.materials_consumed_cost
                else 0.0
            )

    @api.depends('cash_inflow_expected', 'cash_outflow_expected')
    def _compute_cash_deficit(self):
        for rec in self:
            rec.cash_deficit_amount = max(
                0.0, (rec.cash_outflow_expected or 0.0) - (rec.cash_inflow_expected or 0.0)
            )
