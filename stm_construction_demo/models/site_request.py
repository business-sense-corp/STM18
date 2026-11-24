# -*- coding: utf-8 -*-
from markupsafe import Markup
from odoo import api, fields, models
from odoo.exceptions import UserError


class ConstructionSiteRequest(models.Model):
    _name = 'construction.site.request'
    _description = 'طلب مواد الموقع'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    @api.model
    def _default_sar_currency(self):
        sar = self.env['res.currency'].search(
            [('name', '=', 'SAR'), ('active', '=', True)], limit=1
        )
        return sar or self.env.company.currency_id

    name = fields.Char(
        string='رقم الطلب',
        required=True,
        copy=False,
        readonly=True,
        default='جديد',
    )
    project_id = fields.Many2one(
        'project.project',
        string='المشروع',
        required=True,
        tracking=True,
    )
    boq_id = fields.Many2one(
        'construction.boq',
        string='المقايسة (BOQ)',
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
    )
    requested_by_id = fields.Many2one(
        'res.users',
        string='مقدم الطلب',
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    approved_by_id = fields.Many2one(
        'res.users',
        string='المعتمد بواسطة',
        readonly=True,
        tracking=True,
    )
    request_date = fields.Date(
        string='تاريخ الطلب',
        default=fields.Date.context_today,
        required=True,
        tracking=True,
    )
    vendor_id = fields.Many2one(
        'res.partner',
        string='المورد المقترح',
        tracking=True,
    )
    delivery_mode = fields.Selection(
        [
            ('direct_site', 'شراء مباشر إلى موقع المشروع'),
            ('from_main_wh', 'تحويل مخزني من المخزن الرئيسي إلى الموقع (نقل)'),
            ('site_consumption', 'صرف مواد واستهلاك فعلي بالموقع (استهلاك)'),
        ],
        string='آلية التوريد / الصرف',
        default='from_main_wh',
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ('draft', 'مسودة'),
            ('submitted', 'بانتظار اعتماد مدير المشروع'),
            ('approved', 'معتمد'),
            ('done', 'تم التنفيذ'),
            ('rejected', 'مرفوض'),
        ],
        string='الحالة',
        default='draft',
        required=True,
        tracking=True,
    )
    rejection_reason = fields.Text(string='سبب الرفض', tracking=True)
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='طلب الشراء (RFQ)',
        readonly=True,
        copy=False,
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='الإذن المخزني',
        readonly=True,
        copy=False,
    )
    notes = fields.Text(string='ملاحظات الموقع')
    line_ids = fields.One2many(
        'construction.site.request.line',
        'request_id',
        string='بنود المواد المطلوبة',
    )
    total_estimated_cost = fields.Monetary(
        string='التكلفة التقديرية الإجمالية',
        currency_field='currency_id',
        compute='_compute_total_estimated_cost',
        store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'جديد':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('construction.site.request')
                    or 'SRQ/2026/0001'
                )
        return super().create(vals_list)

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id:
            if self.project_id.stm_boq_id:
                self.boq_id = self.project_id.stm_boq_id
            if self.project_id.company_id:
                self.company_id = self.project_id.company_id

    @api.depends('line_ids.estimated_subtotal')
    def _compute_total_estimated_cost(self):
        for rec in self:
            rec.total_estimated_cost = sum(rec.line_ids.mapped('estimated_subtotal'))

    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError('يرجى إضافة صنف واحد على الأقل قبل إرسال الطلب للاعتماد.')
            rec.state = 'submitted'
            rec.message_post(body='تم إرسال طلب المواد لاعتماد مدير المشروع.')
        return True

    def action_approve(self):
        for rec in self:
            rec.write(
                {
                    'state': 'approved',
                    'approved_by_id': self.env.user.id,
                }
            )
            rec.message_post(body=f'تم اعتماد طلب المواد بواسطة {self.env.user.name}.')
        return True

    def action_reject(self):
        for rec in self:
            if not rec.rejection_reason:
                raise UserError('يرجى كتابة سبب الرفض في خانة "سبب الرفض" قبل رفض الطلب.')
            rec.state = 'rejected'
            rec.message_post(body=f'تم رفض الطلب. السبب: {rec.rejection_reason}')
        return True

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        return True

    def action_create_rfq(self):
        PurchaseOrder = self.env['purchase.order']
        for rec in self:
            if rec.state != 'approved':
                raise UserError('يجب اعتماد الطلب أولاً قبل إنشاء طلب الشراء (RFQ).')
            if rec.purchase_order_id:
                raise UserError('تم إنشاء طلب شراء مرتبط بهذا الطلب بالفعل.')
            if not rec.line_ids:
                raise UserError('لا توجد بنود مواد لإنشاء طلب الشراء.')
            if not rec.vendor_id:
                raise UserError('يرجى تحديد "المورد المقترح" أولاً لإنشاء طلب الشراء (RFQ).')

            mode_label = dict(rec._fields['delivery_mode'].selection).get(rec.delivery_mode, '')
            order_lines = []
            for line in rec.line_ids:
                order_lines.append(
                    (
                        0,
                        0,
                        {
                            'product_id': line.product_id.id,
                            'name': line.description or line.product_id.display_name,
                            'product_qty': line.qty,
                            'product_uom': line.uom_id.id,
                            'price_unit': line.estimated_unit_cost,
                            'date_planned': fields.Datetime.now(),
                        },
                    )
                )

            po = PurchaseOrder.create(
                {
                    'partner_id': rec.vendor_id.id,
                    'company_id': rec.company_id.id,
                    'currency_id': rec.currency_id.id,
                    'origin': f'{rec.name} — {rec.project_id.name}',
                    'project_id': rec.project_id.id,
                    'notes': f'طلب مواد موقع: {rec.name} | الآلية: {mode_label}',
                    'order_line': order_lines,
                }
            )
            rec.write(
                {
                    'purchase_order_id': po.id,
                    'state': 'done',
                }
            )
            rec.message_post(body=Markup('تم إنشاء طلب الشراء (RFQ): <b>%s</b>.') % po.name)
        return self.action_view_purchase_order()

    def _get_or_create_site_location(self, warehouse, project):
        Location = self.env['stock.location']
        loc_name = f'موقع: {project.name}'
        loc = Location.search(
            [
                ('name', '=', loc_name),
                ('usage', '=', 'internal'),
                ('company_id', '=', self.company_id.id),
            ],
            limit=1,
        )
        if not loc:
            loc = Location.create(
                {
                    'name': loc_name,
                    'usage': 'internal',
                    'location_id': warehouse.view_location_id.id,
                    'company_id': self.company_id.id,
                }
            )
        return loc

    def action_create_stock_picking(self):
        Picking = self.env['stock.picking']
        Location = self.env['stock.location']
        for rec in self:
            if rec.state != 'approved':
                raise UserError('يجب اعتماد الطلب أولاً قبل إنشاء الإذن المخزني.')
            if rec.picking_id:
                raise UserError('تم إنشاء إذن مخزني مرتبط بهذا الطلب بالفعل.')
            if not rec.line_ids:
                raise UserError('لا توجد بنود مواد لإنشاء الإذن المخزني.')

            warehouse = self.env['stock.warehouse'].search(
                [('company_id', '=', rec.company_id.id)], limit=1
            ) or self.env['stock.warehouse'].search([], limit=1)
            if not warehouse:
                raise UserError('لا يوجد مستودع مخزني معرّف في النظام.')

            site_loc = rec._get_or_create_site_location(warehouse, rec.project_id)
            picking_type = warehouse.int_type_id or warehouse.out_type_id

            if rec.delivery_mode == 'from_main_wh':
                location_src = warehouse.lot_stock_id
                location_dest = site_loc
                origin_label = f'{rec.name} — نقل للموقع (ليس استهلاكاً)'
                note_text = 'تحويل مخزني من المخزن الرئيسي إلى موقع المشروع — نقل مخزني وليس استهلاكاً فعلياً.'
            else:
                prod_loc = Location.search(
                    [
                        ('usage', '=', 'production'),
                        ('company_id', 'in', [rec.company_id.id, False]),
                    ],
                    limit=1,
                ) or self.env.ref('stock.stock_location_customers')
                location_src = warehouse.lot_stock_id
                location_dest = prod_loc
                origin_label = f'{rec.name} — صرف استهلاك فعلي بالموقع'
                note_text = 'صرف مواد واستهلاك فعلي بموقع المشروع (استهلاك نهائي على المشروع).'

            move_vals = []
            for line in rec.line_ids:
                move_vals.append(
                    (
                        0,
                        0,
                        {
                            'name': line.description or line.product_id.display_name,
                            'product_id': line.product_id.id,
                            'product_uom_qty': line.qty,
                            'product_uom': line.uom_id.id,
                            'location_id': location_src.id,
                            'location_dest_id': location_dest.id,
                            'company_id': rec.company_id.id,
                        },
                    )
                )

            picking = Picking.create(
                {
                    'picking_type_id': picking_type.id,
                    'location_id': location_src.id,
                    'location_dest_id': location_dest.id,
                    'origin': origin_label,
                    'note': note_text,
                    'company_id': rec.company_id.id,
                    'project_id': rec.project_id.id,
                    'move_ids': move_vals,
                }
            )
            picking.action_confirm()
            rec.write(
                {
                    'picking_id': picking.id,
                    'state': 'done',
                }
            )
            rec.message_post(
                body=Markup('تم إنشاء الإذن المخزني <b>%s</b> (%s).') % (picking.name, origin_label)
            )
        return self.action_view_picking()

    def action_view_purchase_order(self):
        self.ensure_one()
        if not self.purchase_order_id:
            raise UserError('لا يوجد طلب شراء مرتبط بهذا الطلب.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'طلب الشراء (RFQ)',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': self.purchase_order_id.id,
        }

    def action_view_picking(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError('لا يوجد إذن مخزني مرتبط بهذا الطلب.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'الإذن المخزني',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.picking_id.id,
        }


class ConstructionSiteRequestLine(models.Model):
    _name = 'construction.site.request.line'
    _description = 'بند طلب مواد الموقع'
    _order = 'id'

    request_id = fields.Many2one(
        'construction.site.request',
        string='طلب المواد',
        required=True,
        ondelete='cascade',
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='request_id.currency_id',
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='الصنف / المادة',
        required=True,
    )
    description = fields.Char(string='الوصف')
    qty = fields.Float(string='الكمية', default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', string='الوحدة', required=True)
    estimated_unit_cost = fields.Monetary(
        string='التكلفة التقديرية للوحدة',
        currency_field='currency_id',
    )
    estimated_subtotal = fields.Monetary(
        string='الإجمالي التقديري',
        currency_field='currency_id',
        compute='_compute_subtotal',
        store=True,
    )

    @api.depends('qty', 'estimated_unit_cost')
    def _compute_subtotal(self):
        for line in self:
            line.estimated_subtotal = (line.qty or 0.0) * (line.estimated_unit_cost or 0.0)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.display_name
            self.uom_id = self.product_id.uom_id
            self.estimated_unit_cost = self.product_id.standard_price
