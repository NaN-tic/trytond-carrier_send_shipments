# This file is part of the carrier_send_shipments module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from datetime import datetime
from dateutil.relativedelta import relativedelta
from trytond.model import ModelView, fields
from trytond.wizard import Button, StateTransition, StateView, Wizard

__all__ = ['StockManifestStart', 'StockEnterManifest', 'StockManifest']


class StockManifestStart(ModelView):
    'Stock Manifest Start'
    __name__ = 'stock.manifest.start'
    carrier_api = fields.Many2One('carrier.api', 'Carrier API', required=True)
    from_date = fields.DateTime('From Date', required=True)
    to_date = fields.DateTime('To Date', required=True)

    @staticmethod
    def default_from_date():
        return datetime.now()

    @staticmethod
    def default_to_date():
        return datetime.now() + relativedelta(days=1)


class StockEnterManifest(ModelView):
    'Stock Enter Manifest'
    __name__ = 'stock.enter.manifest'
    manifest = fields.Binary('Manifest')


class StockManifest(Wizard):
    'Stock Manifest'
    __name__ = 'stock.manifest'
    start = StateView('stock.manifest.start',
        'carrier_send_shipments.stock_manifest_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Get Manifest', 'manifest', 'tryton-ok', default=True),
            ])
    manifest = StateTransition()
    enter = StateView('stock.enter.manifest',
        'carrier_send_shipments.stock_enter_manifest_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Done', 'done', 'tryton-ok', default=True),
            ])
    done = StateTransition()

    def transition_manifest(self):
        api = self.start.carrier_api
        from_date = self.start.carrier_api
        to_date = self.start.to_date
        get_manifest = getattr(self, 'get_manifest_' + api.method, False)
        if get_manifest:
            self.enter.manifest = get_manifest(api, from_date, to_date)
        return 'enter'

    def transition_done(self):
        return 'end'
