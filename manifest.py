# This file is part of the carrier_send_shipments module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from datetime import datetime, time
from dateutil.relativedelta import relativedelta
from trytond.model import ModelView, fields
from trytond.wizard import Button, StateTransition, StateView, Wizard
from trytond.transaction import Transaction
from trytond.pool import Pool
import logging
import tempfile

__all__ = ['CarrierManifestStart', 'CarrierEnterManifest', 'CarrierManifest']


class CarrierManifestStart(ModelView):
    'Carrier Manifest Start'
    __name__ = 'carrier.manifest.start'
    carrier_api = fields.Many2One('carrier.api', 'Carrier API', required=True)
    from_date = fields.DateTime('From Date', required=True)
    to_date = fields.DateTime('To Date', required=True)

    @staticmethod
    def default_from_date():
        today = datetime.now()
        return datetime.combine(today, time(0, 0))

    @staticmethod
    def default_to_date():
        tomorrow = datetime.now() + relativedelta(days=1)
        return datetime.combine(tomorrow, time(0, 0))


class CarrierEnterManifest(ModelView):
    'Carrier Enter Manifest'
    __name__ = 'carrier.result.manifest'
    manifest = fields.Binary('Manifest', filename='file_name')
    file_name = fields.Text('File Name')


class CarrierManifest(Wizard):
    'Carrier Manifest'
    __name__ = 'carrier.manifest'
    start = StateView('carrier.manifest.start',
        'carrier_send_shipments.carrier_manifest_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Get Manifest', 'manifest', 'tryton-ok', default=True),
            ])
    manifest = StateTransition()
    result = StateView('carrier.result.manifest',
        'carrier_send_shipments.carrier_manifest_result_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            ])

    @classmethod
    def __setup__(cls):
        super(CarrierManifest, cls).__setup__()
        cls._error_messages.update({
                'not_manifest': 'Not available manifest "%s" carrier.',
                })

    def default_result(self, fields):
        return {
            'manifest': self.result.manifest,
            'file_name': self.result.file_name,
            }

    def transition_manifest(self):
        Date = Pool().get('ir.date')

        api = self.start.carrier_api
        from_date = self.start.from_date
        to_date = self.start.to_date
        dbname = Transaction().cursor.dbname

        get_manifest = getattr(self, 'get_manifest_' + api.method, False)
        if not get_manifest:
            self.raise_user_error('not_manifest', api.method)
        manifest_file = get_manifest(api, from_date, to_date)

        with tempfile.NamedTemporaryFile(
                prefix='%s-manifest-%s-' % (dbname, api.method),
                suffix='.pdf', delete=False) as temp:
            temp.write(manifest_file)
        temp.close()
        logging.getLogger('Carrier').info(
            'Generated manifest file %s' % (temp.name))

        self.result.manifest = buffer(open(temp.name, "rb").read())
        self.result.file_name = temp.name.split('/')[2]
        return 'result'
