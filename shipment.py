# This file is part of the carrier_send_shipments module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from datetime import datetime
from trytond.model import ModelView, fields
from trytond.wizard import (Wizard, StateTransition, StateView, Button,
    StateAction)
from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.pyson import Bool, Eval, Not, Equal
import logging
import tarfile
import tempfile

__all__ = ['Configuration', 'ShipmentOut', 'CarrierSendShipmentsStart',
    'CarrierSendShipmentsResult', 'CarrierSendShipments',
    'CarrierPrintShipmentStart', 'CarrierPrintShipmentResult',
    'CarrierPrintShipment', 'CarrierGetLabelStart', 'CarrierGetLabelResult',
    'CarrierGetLabel']

_SHIPMENT_STATES = ['packed', 'done']
logger = logging.getLogger(__name__)


class Configuration(metaclass=PoolMeta):
    __name__ = 'stock.configuration'
    attach_label = fields.Boolean('Attach Label')


class ShipmentOut(metaclass=PoolMeta):
    __name__ = 'stock.shipment.out'
    phone = fields.Function(fields.Char('Phone'), 'get_mechanism')
    mobile = fields.Function(fields.Char('Mobile'), 'get_mechanism')
    fax = fields.Function(fields.Char('Fax'), 'get_mechanism')
    email = fields.Function(fields.Char('E-Mail'), 'get_mechanism')
    carrier_service_domain = fields.Function(fields.One2Many(
            'carrier.api.service', None, 'Carrier Domain',
            depends=['carrier']),
        'on_change_with_carrier_service_domain')
    carrier_service = fields.Many2One('carrier.api.service',
        'Carrier API Service',
        domain=[
            ('id', 'in', Eval('carrier_service_domain')),
            ],
        states={
            'readonly': Equal(Eval('state'), 'done'),
            'invisible': ~Eval('carrier'),
            }, depends=['carrier', 'state', 'carrier_service_domain'])
    carrier_delivery = fields.Boolean('Delivered', readonly=True,
        states={
            'invisible': ~Eval('carrier'),
            },
        help='The package has been delivered')
    carrier_printed = fields.Boolean('Printed', readonly=True,
        states={
            'invisible': ~Eval('carrier'),
            },
        help='Picking is already printed')
    carrier_notes = fields.Char('Carrier Notes',
        states={
            'readonly': Equal(Eval('state'), 'done'),
            'invisible': ~Eval('carrier'),
            },
        help='Add notes when send API shipment')
    carrier_weight = fields.Function(fields.Float('Carrier Weight',
        digits=(16, Eval('weight_digits', 2)),
        depends=['weight_digits']), 'on_change_with_carrier_weight')
    carrier_weight_uom = fields.Function(fields.Many2One('product.uom',
        'Carrier Weight UOM'), 'on_change_with_carrier_weight_uom')
    carrier_send_employee = fields.Many2One('company.employee', 'Carrier Send Employee', readonly=True)
    carrier_send_date = fields.DateTime('Carrier Send Date', readonly=True)

    @classmethod
    def __setup__(cls):
        super(ShipmentOut, cls).__setup__()
        if 'carrier' not in cls.carrier_cashondelivery_total.depends:
            cls.carrier_cashondelivery_total.depends.append('carrier')
        cls._buttons.update({
                'wizard_carrier_send_shipments': {
                    'invisible': (~Eval('state').in_(_SHIPMENT_STATES)) |
                        (Eval('carrier_delivery')) |
                        Not(Bool(Eval('carrier'))),
                    },
                'wizard_carrier_print_shipment': {
                    'invisible': (~Eval('state').in_(_SHIPMENT_STATES)) |
                        (Eval('carrier_printed')) | Not(Bool(Eval('carrier'))),
                    },
                })

    def _comment2txt(self, comment):
        return comment.replace('\n', '. ').replace('\r', '')

    @fields.depends('carrier')
    def on_change_with_carrier_service_domain(self, name=None):
        ApiCarrier = Pool().get('carrier.api-carrier.carrier')
        carrier_api_services = []
        if self.carrier:
            api_carriers = ApiCarrier.search([
                    ('carrier', '=', self.carrier.id)])
            carrier_api_services = [service.id for api_carrier in api_carriers
                for service in api_carrier.api.services]
        return carrier_api_services

    @fields.depends('weight_func', 'carrier')
    def on_change_with_carrier_weight(self, name=None):
        Uom = Pool().get('product.uom')

        if not hasattr(self, 'weight_func'):
            return 1.0

        weight = self.weight_func
        if weight == 0 or weight == 0.0:
            weight = 1.0

        if self.carrier and self.carrier.apis:
            api = self.carrier.apis[0]
            if self.weight_uom:
                weight = Uom.compute_qty(
                    self.weight_uom, weight, api.weight_api_unit)
            elif api.weight_unit:
                weight = Uom.compute_qty(
                    api.weight_unit, weight, api.weight_api_unit)
        return weight

    @fields.depends('carrier')
    def on_change_with_carrier_weight_uom(self, name=None):
        if self.carrier and self.carrier.apis:
            api = self.carrier.apis[0]
            return api.weight_api_unit.id if api.weight_api_unit else None

    def on_change_customer(self):
        super(ShipmentOut, self).on_change_customer()

        carrier_notes = None
        if self.customer:
            address = self.customer.address_get(type='delivery')
            if address.comment_shipment:
                carrier_notes = self._comment2txt(address.comment_shipment)
            elif self.customer.comment_shipment:
                carrier_notes = self._comment2txt(self.customer.comment_shipment)
        self.carrier_notes = carrier_notes

    def on_change_carrier(self):
        super(ShipmentOut, self).on_change_carrier()
        self.carrier_service = None

    @classmethod
    @ModelView.button_action('carrier_send_shipments.'
        'wizard_carrier_send_shipments')
    def wizard_carrier_send_shipments(cls, shipments):
        pass

    @classmethod
    @ModelView.button_action('carrier_send_shipments.'
        'wizard_carrier_print_shipment')
    def wizard_carrier_print_shipment(cls, shipments):
        pass

    @classmethod
    def copy(cls, shipments, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['carrier_delivery'] = None
        default['carrier_printed'] = None
        return super(ShipmentOut, cls).copy(shipments, default=default)

    def get_mechanism(self, name):
        pool = Pool()
        ContactMechanism = pool.get('party.contact_mechanism')

        value = getattr(self.delivery_address, name)
        if value:
            return value

        mechanisms = ContactMechanism.search([
            ('party', '=', self.customer),
            ('type', '=', name),
            ('write_date', '!=', None),
            ], order=[('write_date', 'DESC')], limit=1)
        mechanism_write_date = (mechanisms[0] if mechanisms else None)

        mechanisms = ContactMechanism.search([
            ('party', '=', self.customer),
            ('type', '=', name),
            ], order=[('create_date', 'DESC')], limit=1)
        mechanism_create_date = (mechanisms[0] if mechanisms else None)

        mechanism_value = None
        if mechanism_write_date and mechanism_create_date:
            if (mechanism_write_date.write_date >
                    mechanism_create_date.create_date):
                mechanism_value = mechanism_write_date.value
            else:
                mechanism_value = mechanism_create_date.value
        elif mechanism_create_date and not mechanism_write_date:
            mechanism_value = mechanism_create_date.value
        elif not mechanism_create_date and mechanism_write_date:
            mechanism_value = mechanism_write_date.value
        return mechanism_value

    @staticmethod
    def get_carrier_employee():
        User = Pool().get('res.user')
        if Transaction().context.get('employee'):
            return Transaction().context['employee']
        else:
            user = User(Transaction().user)
            if user.employee:
                return user.employee.id

    @staticmethod
    def get_carrier_date():
        return datetime.now()

    @classmethod
    def send_shipment_api(cls, shipment):
        '''Send Shipmemt to carrier API'''
        pool = Pool()
        Shipment = pool.get('stock.shipment.out')
        API = pool.get('carrier.api')
        Config = pool.get('stock.configuration')
        Attachment = pool.get('ir.attachment')

        config_stock = Config(1)
        attach_label = config_stock.attach_label

        if not shipment.carrier:
            message = gettext('carrier_send_shipments.msg_not_carrier',
                name=shipment.rec_name)
            refs = []
            labs = []
            errs = [message]
            return refs, labs, errs

        apis = API.search([('carriers', 'in', [shipment.carrier.id])],
            limit=1)
        if not apis:
            message = gettext('carrier_send_shipments.msg_not_carrier_api',
                name=shipment.rec_name)
            logger.warning(message)
            refs = []
            labs = []
            errs = [message]
            return refs, labs, errs

        api, = apis

        if not shipment.delivery_address.street or not shipment.delivery_address.zip \
                or not shipment.delivery_address.city or not shipment.delivery_address.country:
            message = gettext('carrier_send_shipments.msg_shipmnet_delivery_address',
                name=shipment.rec_name)
            logger.warning(message)
            refs = []
            labs = []
            errs = [message]
        else:
            send_shipment = getattr(Shipment, 'send_%s' % api.method)
            refs, labs, errs = send_shipment(api, [shipment])

            if attach_label and labs:
                attach = Attachment(
                    name=datetime.now().strftime("%y/%m/%d %H:%M:%S"),
                    type='data',
                    data=fields.Binary.cast(open(labs[0], "rb").read()),
                    resource=str(shipment))
                attach.save()
        return refs, labs, errs


class CarrierSendShipmentsStart(ModelView):
    'Carrier Send Shipments Start'
    __name__ = 'carrier.send.shipments.start'
    shipments = fields.Many2Many('stock.shipment.out', None, None,
        'Shipments', readonly=True)


class CarrierSendShipmentsResult(ModelView):
    'Carrier Send Shipments Result'
    __name__ = 'carrier.send.shipments.result'
    info = fields.Text('Info', readonly=True)
    labels = fields.Binary('Labels', filename='file_name')
    file_name = fields.Text('File Name')


class CarrierSendShipments(Wizard):
    'Carrier Send Shipments'
    __name__ = "carrier.send.shipments"
    start = StateView('carrier.send.shipments.start',
        'carrier_send_shipments.carrier_send_shipments_start', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Send', 'send', 'tryton-ok', default=True),
            ])
    send = StateTransition()
    result = StateView('carrier.send.shipments.result',
        'carrier_send_shipments.carrier_send_shipments_result', [
            Button('Close', 'end', 'tryton-close'),
            ])
    print_ = StateAction(
        'carrier_send_shipments.wizard_carrier_print_shipment')

    def transition_send(self):
        Shipment = Pool().get('stock.shipment.out')

        dbname = Transaction().database.name
        context = Transaction().context

        info = None
        carrier_labels = None
        file_name = None
        references = []
        labels = []
        errors = []

        active_ids = context.get('active_ids')
        if active_ids:
            for shipment in Shipment.browse(active_ids):
                refs, labs, errs = Shipment.send_shipment_api(shipment)

                references += refs
                labels += labs
                errors += errs

            #  Save results in info and labels fields
            info = gettext('carrier_send_shipments.msg_shipment_info',
                references=', '.join(references) if references else '',
                errors=', '.join(errors) if errors else '')

            #  Save file label in labels field
            if len(labels) == 1:  # A label generate simple file
                label, = labels
                carrier_labels = fields.Binary.cast(open(label, "rb").read())
                file_name = label.split('/')[2]
            elif len(labels) > 1:  # Multiple labels generate tgz
                temp = tempfile.NamedTemporaryFile(prefix='%s-carrier-' % dbname,
                    delete=False)
                temp.close()
                with tarfile.open(temp.name, "w:gz") as tar:
                    for path_label in labels:
                        tar.add(path_label)
                tar.close()
                carrier_labels = fields.Binary.cast(open(temp.name, "rb").read())
                file_name = '%s.tgz' % temp.name.split('/')[2]

        self.result.info = info
        self.result.labels = carrier_labels
        self.result.file_name = file_name

        return 'result'

    def default_start(self, fields):
        Shipment = Pool().get('stock.shipment.out')

        context = Transaction().context

        active_ids = context.get('active_ids')
        if active_ids:
            # validate some shipment data before to send carrier API
            for shipment in Shipment.browse(active_ids):
                if not shipment.state in _SHIPMENT_STATES:
                    raise UserError(gettext('carrier_send_shipments.msg_shipment_state',
                        shipment=shipment.number,
                        state=shipment.state,
                        states=', '.join(_SHIPMENT_STATES)))
                if not shipment.carrier:
                    raise UserError(gettext('carrier_send_shipments.msg_add_carrier',
                        shipment=shipment.number))
                if shipment.carrier_tracking_ref:
                    raise UserError(gettext('carrier_send_shipments.msg_shipment_sended',
                        shipment=shipment.number))
                if not shipment.carrier.apis:
                    raise UserError(gettext('carrier_send_shipments.msg_add_carrier_api',
                        carrier=shipment.carrier.rec_name))
                api, = shipment.carrier.apis
                if api.zips:
                    zips = api.zips.split(',')
                    if (shipment.delivery_address.zip
                            and shipment.delivery_address.zip in zips):
                        raise UserError(gettext('carrier_send_shipments.msg_shipment_zip',
                            shipment=shipment.number,
                            zip=shipment.delivery_address.zip))

        default = {}
        default['shipments'] = active_ids
        return default

    def default_result(self, fields):
        return {
            'info': self.result.info,
            'labels': self.result.labels,
            'file_name': self.result.file_name,
            }

    def do_print_(self, action):
        active_ids = Transaction().context['active_ids']
        return action, {'ids': active_ids}


class CarrierPrintShipmentStart(ModelView):
    'Carrier Print Shipment Start'
    __name__ = 'carrier.print.shipment.start'
    shipments = fields.Many2Many('stock.shipment.out', None, None,
        'Shipments', readonly=True)

    @staticmethod
    def default_shipments():
        return Transaction().context.get('active_ids')


class CarrierPrintShipmentResult(ModelView):
    'Carrier Print Shipment Result'
    __name__ = 'carrier.print.shipment.result'
    labels = fields.Binary('Labels', filename='file_name')
    file_name = fields.Char('File Name')


class CarrierPrintShipment(Wizard):
    'Carrier Print Shipment'
    __name__ = "carrier.print.shipment"
    start = StateView('carrier.print.shipment.start',
        'carrier_send_shipments.carrier_print_shipment_start', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Print', 'print_', 'tryton-ok', default=True),
            ])
    print_ = StateTransition()
    result = StateView('carrier.print.shipment.result',
        'carrier_send_shipments.carrier_print_shipment_result', [
            Button('Close', 'end', 'tryton-close'),
            ])

    def default_start(self, fields):
        Shipment = Pool().get('stock.shipment.out')

        context = Transaction().context

        active_ids = context.get('active_ids')
        if active_ids:
            # validate some shipment data before to send carrier API
            for shipment in Shipment.browse(active_ids):
                if not shipment.carrier_tracking_ref:
                    raise UserError(gettext('carrier_send_shipments.msg_shipment_not_tracking_ref',
                        shipment=shipment.number))

        default = {}
        default['shipments'] = active_ids
        return default

    def default_result(self, fields):
        return {
            'labels': self.result.labels,
            'file_name': self.result.file_name,
            }

    def transition_print_(self):
        pool = Pool()
        Shipment = pool.get('stock.shipment.out')
        API = pool.get('carrier.api')
        Attachment = pool.get('ir.attachment')
        Config = pool.get('stock.configuration')

        config_stock = Config(1)
        attach_label = config_stock.attach_label

        dbname = Transaction().database.name
        labels = []

        shipments = Shipment.search([
                ('id', 'in', Transaction().context['active_ids']),
                ])
        for shipment in shipments:
            apis = API.search([('carriers', 'in', [shipment.carrier.id])],
                limit=1)
            if not apis:
                continue
            api, = apis

            print_label = getattr(Shipment, 'print_labels_%s' % api.method)
            labs = print_label(api, [shipment])

            if attach_label and labs:
                attach = Attachment(
                    name=datetime.now().strftime("%y/%m/%d %H:%M:%S"),
                    type='data',
                    data=fields.Binary.cast(open(labs[0], "rb").read()),
                    resource=str(shipment))
                attach.save()

            labels += labs

        #  Save file label in labels field
        if len(labels) == 1:  # A label generate simple file
            label, = labels
            carrier_labels = fields.Binary.cast(open(label, "rb").read())
            file_name = label.split('/')[2]
        elif len(labels) > 1:  # Multiple labels generate tgz
            temp = tempfile.NamedTemporaryFile(prefix='%s-carrier-' % dbname,
                delete=False)
            temp.close()
            with tarfile.open(temp.name, "w:gz") as tar:
                for path_label in labels:
                    tar.add(path_label)
            tar.close()
            carrier_labels = fields.Binary.cast(open(temp.name, "rb").read())
            file_name = '%s.tgz' % temp.name.split('/')[2]
        else:
            carrier_labels = None
            file_name = None
        self.result.labels = carrier_labels
        self.result.file_name = file_name

        return 'result'


class CarrierGetLabelStart(ModelView):
    'Carrier Get Label Start'
    __name__ = 'carrier.get.label.start'
    codes = fields.Char('Codes', required=True,
        help='Introduce codes or tracking reference of shipments separated by commas.')


class CarrierGetLabelResult(ModelView):
    'Carrier Get Label Result'
    __name__ = 'carrier.get.label.result'
    attachments = fields.One2Many('ir.attachment', None, 'Attachments',
        states={
            'invisible': Not(Bool(Eval('attachments'))),
            'readonly': True,
            })


class CarrierGetLabel(Wizard):
    'Carrier Get Label'
    __name__ = "carrier.get.label"
    start = StateView('carrier.get.label.start',
        'carrier_send_shipments.carrier_get_label_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Get', 'get', 'tryton-ok', default=True),
            ])
    get = StateTransition()
    result = StateView('carrier.get.label.result',
        'carrier_send_shipments.carrier_get_label_result_view_form', [
            Button('Close', 'end', 'tryton-close'),
            ])

    def transition_get(self):
        pool = Pool()
        Attachment = pool.get('ir.attachment')
        Shipment = pool.get('stock.shipment.out')
        API = pool.get('carrier.api')

        codes = [l.strip() for l in self.start.codes.split(',')]
        shipments = Shipment.search([
                ('state', 'in', _SHIPMENT_STATES),
                ['OR',
                    ('code', 'in', codes),
                    ('carrier_tracking_ref', 'in', codes),
                ]])

        if not shipments:
            return 'result'

        apis = {}
        for shipment in shipments:
            if not shipment.carrier:
                continue
            carrier_apis = API.search([('carriers', 'in', [shipment.carrier.id])],
                limit=1)
            if not carrier_apis:
                continue
            api, = carrier_apis

            if apis.get(api.method):
                shipments = apis.get(api.method)
                shipments.append(shipment)
            else:
                shipments = [shipment]
            apis[api.method] = shipments

        attachments = []
        for method, shipments in apis.items():
            api, = API.search([('method', '=', method)],
                limit=1)
            print_label = getattr(Shipment, 'print_labels_%s' % method)
            labels = print_label(api, shipments)

            for label, shipment in zip(labels, shipments):
                attach = {
                    'name': datetime.now().strftime("%y/%m/%d %H:%M:%S"),
                    'type': 'data',
                    'data': fields.Binary.cast(open(label, "rb").read()),
                    'description': '%s - %s' % (shipment.number, method),
                    'resource': '%s' % str(shipment),
                    }

                attachments.append(attach)

        attachments = Attachment.create(attachments)
        self.result.attachments = attachments

        return 'result'

    def default_result(self, fields):
        return {
            'attachments': [a.id
                for a in getattr(self.result, 'attachments', [])],
            }
