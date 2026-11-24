# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    stm_boq_id = fields.Many2one(
        'construction.boq',
        string='المقايسة (BOQ)',
        copy=False,
    )
    stm_currency_id = fields.Many2one(
        'res.currency',
        string='عملة المقايسة',
        compute='_compute_stm_currency_id',
    )
    stm_project_type = fields.Selection(
        [
            ('off_plan', 'بيع على الخارطة'),
            ('ready', 'وحدات جاهزة'),
            ('contracting', 'مقاولات للغير'),
        ],
        string='نوع المشروع',
    )
    stm_delay_days = fields.Integer(string='أيام التأخير')
    stm_delay_reason = fields.Text(string='سبب التأخير')
    stm_progress_planned = fields.Float(string='الإنجاز المخطط (%)', default=100.0)
    stm_progress_actual = fields.Float(
        string='الإنجاز الفعلي (%)',
        compute='_compute_stm_boq_metrics',
        store=True,
    )
    stm_budget_planned = fields.Monetary(
        string='الميزانية المخططة',
        currency_field='stm_currency_id',
        compute='_compute_stm_boq_metrics',
        store=True,
    )
    stm_cost_actual = fields.Monetary(
        string='التكلفة الفعلية',
        currency_field='stm_currency_id',
        compute='_compute_stm_boq_metrics',
        store=True,
    )
    stm_cost_etc = fields.Monetary(
        string='تكلفة الإكمال (ETC)',
        currency_field='stm_currency_id',
        compute='_compute_stm_boq_metrics',
        store=True,
    )
    stm_equipment_summary = fields.Text(string='المعدات والآليات بالموقع')
    stm_site_request_count = fields.Integer(
        string='طلبات مواد الموقع',
        compute='_compute_stm_counts',
    )
    stm_task_count = fields.Integer(
        string='المهام التنفيذية',
        compute='_compute_stm_counts',
    )

    @api.depends('stm_boq_id', 'stm_boq_id.currency_id', 'company_id.currency_id')
    def _compute_stm_currency_id(self):
        for rec in self:
            rec.stm_currency_id = (
                rec.stm_boq_id.currency_id
                or rec.company_id.currency_id
                or self.env.company.currency_id
            )

    @api.depends(
        'stm_boq_id',
        'stm_boq_id.progress_percent',
        'stm_boq_id.total_planned',
        'stm_boq_id.total_actual',
        'stm_boq_id.total_etc',
    )
    def _compute_stm_boq_metrics(self):
        for rec in self:
            boq = rec.stm_boq_id
            if boq:
                rec.stm_progress_actual = boq.progress_percent
                rec.stm_budget_planned = boq.total_planned
                rec.stm_cost_actual = boq.total_actual
                rec.stm_cost_etc = boq.total_etc
            else:
                rec.stm_progress_actual = 0.0
                rec.stm_budget_planned = 0.0
                rec.stm_cost_actual = 0.0
                rec.stm_cost_etc = 0.0

    def _compute_stm_counts(self):
        SiteRequest = self.env['construction.site.request']
        Task = self.env['project.task']
        for rec in self:
            rec.stm_site_request_count = SiteRequest.search_count([('project_id', '=', rec.id)])
            rec.stm_task_count = Task.search_count([('project_id', '=', rec.id)])

    def action_view_stm_boq(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'المقايسة (BOQ)',
            'res_model': 'construction.boq',
            'view_mode': 'form',
            'res_id': self.stm_boq_id.id,
        }

    def action_view_stm_site_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'طلبات مواد الموقع',
            'res_model': 'construction.site.request',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {
                'default_project_id': self.id,
                'default_boq_id': self.stm_boq_id.id if self.stm_boq_id else False,
            },
        }


class ProjectTask(models.Model):
    _inherit = 'project.task'

    stm_boq_line_id = fields.Many2one(
        'construction.boq.line',
        string='بند المقايسة',
        copy=False,
    )
    stm_planned_qty = fields.Float(string='الكمية المخططة')
    stm_executed_qty = fields.Float(string='الكمية المنفذة')
    stm_progress_percent = fields.Float(
        string='نسبة الإنجاز (%)',
        compute='_compute_stm_progress',
        store=True,
        readonly=False,
        digits=(5, 2),
    )
    stm_is_delayed = fields.Boolean(string='متأخرة')
    stm_delay_days = fields.Integer(string='أيام التأخير')
    stm_delay_reason = fields.Char(string='سبب التأخير')

    @api.depends('stm_planned_qty', 'stm_executed_qty')
    def _compute_stm_progress(self):
        for task in self:
            if task.stm_planned_qty > 0:
                task.stm_progress_percent = min(
                    100.0, (task.stm_executed_qty / task.stm_planned_qty) * 100.0
                )
            elif not task.stm_progress_percent:
                task.stm_progress_percent = 0.0
