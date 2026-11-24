# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    stm_is_real_estate_unit = fields.Boolean(
        string='وحدة عقارية',
        default=False,
    )
    stm_unit_availability = fields.Selection(
        [
            ('available', 'متاح للبيع'),
            ('reserved', 'محجوز'),
            ('sold', 'مباع'),
        ],
        string='حالة البيع والتوافر',
        default='available',
    )
    stm_handover_readiness = fields.Selection(
        [
            ('under_construction', 'تحت الإنشاء'),
            ('ready', 'جاهز للتسليم'),
            ('handed_over', 'تم التسليم'),
        ],
        string='جاهزية التسليم (مستقلة عن البيع)',
        default='under_construction',
    )
    stm_expected_handover_date = fields.Date(
        string='تاريخ التسليم المتوقع',
    )
    stm_project_id = fields.Many2one(
        'project.project',
        string='المشروع الإنشائي المرتبط',
    )
    stm_unit_cost_id = fields.Many2one(
        'construction.unit.cost',
        string='بطاقة تكلفة البلوك',
    )


class RealEstateContract(models.Model):
    _inherit = 'real.estate.contract'

    # NOTE: real.estate.contract does NOT inherit mail.thread -> never set tracking=True here.
    stm_handover_status = fields.Selection(
        [
            ('pending', 'قيد التجهيز'),
            ('ready', 'جاهز للتسليم'),
            ('approved', 'معتمد للتسليم'),
            ('delivered', 'تم التسليم'),
        ],
        string='حالة التسليم',
        default='pending',
    )
    stm_expected_handover_date = fields.Date(
        string='تاريخ التسليم المتوقع',
    )
    stm_actual_handover_date = fields.Date(
        string='تاريخ التسليم الفعلي',
        readonly=True,
    )
    stm_handover_approved_by = fields.Many2one(
        'res.users',
        string='معتمد التسليم',
        readonly=True,
    )

    # Cost-to-Sale Margin Bridge (never mixing EGP & SAR currencies)
    stm_project_id = fields.Many2one(
        'project.project',
        string='المشروع الإنشائي',
        related='product_id.product_tmpl_id.stm_project_id',
        store=True,
        readonly=False,
    )
    stm_unit_cost_id = fields.Many2one(
        'construction.unit.cost',
        string='بطاقة تكلفة البلوك',
        compute='_compute_stm_unit_cost_id',
        store=True,
        readonly=False,
    )
    stm_unit_cost_currency_id = fields.Many2one(
        'res.currency',
        string='عملة بطاقة التكلفة',
        related='stm_unit_cost_id.currency_id',
        readonly=True,
    )
    stm_expected_unit_cost = fields.Monetary(
        string='التكلفة المتوقعة للوحدة (EAC)',
        currency_field='stm_unit_cost_currency_id',
        related='stm_unit_cost_id.unit_expected_cost',
        readonly=True,
    )
    stm_expected_unit_margin = fields.Monetary(
        string='الهامش المتوقع للوحدة',
        currency_field='stm_unit_cost_currency_id',
        related='stm_unit_cost_id.unit_expected_margin',
        readonly=True,
    )
    stm_expected_unit_margin_pct = fields.Float(
        string='نسبة الهامش المتوقع (%)',
        related='stm_unit_cost_id.unit_expected_margin_pct',
        readonly=True,
    )

    @api.depends('product_id', 'product_id.product_tmpl_id.stm_unit_cost_id', 'stm_project_id')
    def _compute_stm_unit_cost_id(self):
        UnitCost = self.env['construction.unit.cost']
        for rec in self:
            tmpl = rec.product_id.product_tmpl_id if rec.product_id else False
            if tmpl and tmpl.stm_unit_cost_id:
                rec.stm_unit_cost_id = tmpl.stm_unit_cost_id
            elif rec.stm_project_id:
                cost = UnitCost.search([('project_id', '=', rec.stm_project_id.id)], limit=1)
                rec.stm_unit_cost_id = cost
            elif not rec.stm_unit_cost_id:
                rec.stm_unit_cost_id = False

    def action_stm_handover_ready(self):
        for rec in self:
            rec.stm_handover_status = 'ready'
            if rec.product_id and rec.product_id.product_tmpl_id.stm_handover_readiness == 'under_construction':
                rec.product_id.product_tmpl_id.stm_handover_readiness = 'ready'

    def action_stm_handover_approve(self):
        for rec in self:
            rec.write({
                'stm_handover_status': 'approved',
                'stm_handover_approved_by': self.env.user.id,
            })

    def action_stm_handover_deliver(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.write({
                'stm_handover_status': 'delivered',
                'stm_actual_handover_date': today,
            })
            if rec.product_id:
                rec.product_id.product_tmpl_id.write({
                    'stm_handover_readiness': 'handed_over',
                    'stm_unit_availability': 'sold',
                })


class ProjectProjectRealEstateBridge(models.Model):
    _inherit = 'project.project'

    stm_unit_count = fields.Integer(
        string='الوحدات العقارية',
        compute='_compute_stm_real_estate_counts',
    )
    stm_unit_cost_count = fields.Integer(
        string='بطاقات ربحية البلوك',
        compute='_compute_stm_real_estate_counts',
    )

    def _compute_stm_real_estate_counts(self):
        ProductTmpl = self.env['product.template']
        UnitCost = self.env['construction.unit.cost']
        for rec in self:
            rec.stm_unit_count = ProductTmpl.search_count([
                ('stm_project_id', '=', rec.id),
                ('stm_is_real_estate_unit', '=', True),
            ])
            rec.stm_unit_cost_count = UnitCost.search_count([
                ('project_id', '=', rec.id),
            ])

    def action_view_stm_units(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'الوحدات العقارية للمشروع',
            'res_model': 'product.template',
            'view_mode': 'kanban,list,form',
            'domain': [
                ('stm_project_id', '=', self.id),
                ('stm_is_real_estate_unit', '=', True),
            ],
            'context': {
                'default_stm_project_id': self.id,
                'default_stm_is_real_estate_unit': True,
            },
        }

    def action_view_stm_unit_costs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'ربحية البلوك والوحدة',
            'res_model': 'construction.unit.cost',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
