# This file is part of the carrier_send_shipments module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from datetime import datetime
from trytond.model import ModelSQL, ModelView, fields
from trytond.wizard import (Wizard, StateTransition, StateView, Button,
    StateAction)
from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.report import Report
from trytond.pyson import Bool, Eval, Not, Equal
from trytond.config import config
from trytond.tools import slugify
from trytond.rpc import RPC
import logging
import tarfile
import tempfile


_SHIPMENT_STATES = ['packed', 'done']
_SHIPMENT_RETURN_STATES = ['draft']

logger = logging.getLogger(__name__)

if config.getboolean('carrier_send_shipments', 'filestore', default=False):
    file_id = 'carrier_tracking_label_id'
    store_prefix = config.get('carrier_send_shipments', 'store_prefix',
        default=None)
else:
    file_id = None
    store_prefix = None


class CarrierSendShipmentsMixin(ModelSQL, ModelView):
    phone = fields.Function(fields.Char('Phone'), 'get_mechanism')
    mobile = fields.Function(fields.Char('Mobile'), 'get_mechanism')
    fax = fields.Function(fields.Char('Fax'), 'get_mechanism')
    email = fields.Function(fields.Char('E-Mail'), 'get_mechanism')
    carrier_service_domain = fields.Function(fields.One2Many(
            'carrier.api.service', None, 'Carrier Domain'),
        'on_change_with_carrier_service_domain',
        setter='set_carrier_service_domain')
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
    carrier_send_employee = fields.Many2One('company.employee',
        'Carrier Send Employee', readonly=True)
    carrier_send_date = fields.DateTime('Carrier Send Date', readonly=True)
    carrier_tracking_label = fields.Binary('Carrier Tracking Label',
        readonly=True, file_id=file_id, store_prefix=store_prefix)
    carrier_tracking_label_id = fields.Char('Carrier Tracking Label ID',
        readonly=True)

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

    @classmethod
    def set_carrier_service_domain(cls, shipments, name, value):
        # maybe is a bug client since 5.6
        pass

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
        super(CarrierSendShipmentsMixin, self).on_change_customer()

        carrier_notes = None
        if self.customer:
            address = self.customer.address_get(type='delivery')
            if address and address.comment_shipment:
                carrier_notes = self._comment2txt(address.comment_shipment)
            elif self.customer.comment_shipment:
                carrier_notes = self._comment2txt(
                    self.customer.comment_shipment)
        self.carrier_notes = carrier_notes

    def on_change_carrier(self):
        try:
            super(CarrierSendShipmentsMixin, self).on_change_carrier()
        except AttributeError:
            pass
        self.carrier_service = None

    @classmethod
    def copy(cls, shipments, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['carrier_delivery'] = None
        default['carrier_printed'] = None
        default['carrier_tracking_label'] = None
        default['carrier_tracking_label_id'] = None
        return super(CarrierSendShipmentsMixin, cls).copy(shipments, default=default)

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
        API = pool.get('carrier.api')
        ModelData = pool.get('ir.model.data')
        ActionReport = pool.get('ir.action.report')

        active_model = shipment.__name__
        Shipment = pool.get(active_model)

        if not shipment.carrier:
            message = gettext('carrier_send_shipments.msg_not_carrier',
                name=shipment.rec_name)
            return [], [], [message]

        apis = API.search([('carriers', 'in', [shipment.carrier.id])],
            limit=1)
        if not apis:
            message = gettext('carrier_send_shipments.msg_not_carrier_api',
                name=shipment.rec_name)
            logger.warning(message)
            return [], [], [message]

        api, = apis

        if (not shipment.delivery_address.street
                or not shipment.delivery_address.postal_code
                or not shipment.delivery_address.city
                or not shipment.delivery_address.country):
            message = gettext(
                'carrier_send_shipments.msg_shipmnet_delivery_address',
                name=shipment.rec_name)
            logger.warning(message)
            return [], [], [message]

        send_shipment = getattr(Shipment, 'send_%s' % api.method)
        refs, labs, errs = send_shipment(api, [shipment])
        if errs:
            return refs, labs, errs

        # call report
        if active_model == 'stock.shipment.out':
            action_id = ModelData.get_id('carrier_send_shipments', 'report_label')
            action_report = ActionReport(action_id)
            Report = pool.get(action_report.report_name, type='report')
            Report.execute([shipment], {
                'model': 'stock.shipment.out',
                'id': shipment.id,
                'ids': [shipment.id],
                'action_id': action_id,
                })
        return refs, labs, errs


class ShipmentOut(CarrierSendShipmentsMixin, metaclass=PoolMeta):
    __name__ = 'stock.shipment.out'

    @classmethod
    def __setup__(cls):
        super(ShipmentOut, cls).__setup__()
        if hasattr(cls, 'carrier_cashondelivery_total'):
            if 'carrier' not in cls.carrier_cashondelivery_total.depends:
                cls.carrier_cashondelivery_total.depends.add('carrier')
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


class ShipmentOutReturn(CarrierSendShipmentsMixin, metaclass=PoolMeta):
    __name__ = 'stock.shipment.out.return'
    carrier = fields.Many2One('carrier', 'Carrier', states={
            'readonly': ~Eval('state').in_(['draft', 'waiting', 'assigned',
                    'packed']),
            },
        depends=['state'])

    @classmethod
    def __setup__(cls):
        super(ShipmentOutReturn, cls).__setup__()
        cls._buttons.update({
                'wizard_carrier_send_shipments_return': {
                    'invisible': (~Eval('state').in_(_SHIPMENT_RETURN_STATES)) |
                        (Eval('carrier_delivery')) |
                        Not(Bool(Eval('carrier'))),
                    },
                })

    @classmethod
    @ModelView.button_action('carrier_send_shipments.'
        'wizard_carrier_send_shipments_return')
    def wizard_carrier_send_shipments_return(cls, shipments):
        pass


class CarrierSendShipmentsStart(ModelView):
    'Carrier Send Shipments Start'
    __name__ = 'carrier.send.shipments.start'
    shipments = fields.Many2Many('stock.shipment.out', None, None,
        'Shipments', readonly=True,
        states={
            'invisible': Bool(Eval('shipment_returns')),
        }, depends=['shipment_returns'])
    shipment_returns = fields.Many2Many('stock.shipment.out.return', None, None,
        'Shipment Returns', readonly=True,
        states={
            'invisible': Bool(Eval('shipments')),
        }, depends=['shipments'])


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
        context = Transaction().context
        active_model = context.get('active_model')
        active_ids = context.get('active_ids')

        Shipment = Pool().get(active_model)

        dbname = Transaction().database.name
        context = Transaction().context

        info = None
        carrier_labels = None
        file_name = None
        references = []
        labels = []
        errors = []

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
                temp = tempfile.NamedTemporaryFile(
                    prefix='%s-carrier-' % dbname, delete=False)
                temp.close()
                with tarfile.open(temp.name, "w:gz") as tar:
                    for path_label in labels:
                        tar.add(path_label)
                tar.close()
                carrier_labels = fields.Binary.cast(
                    open(temp.name, "rb").read())
                file_name = '%s.tgz' % temp.name.split('/')[2]

        self.result.info = info
        self.result.labels = carrier_labels
        self.result.file_name = file_name

        return 'result'

    def default_start(self, fields):
        context = Transaction().context
        active_model = context.get('active_model')
        active_ids = context.get('active_ids')

        Shipment = Pool().get(active_model)

        if active_model == 'stock.shipment.out.return':
            states = _SHIPMENT_RETURN_STATES
        else:
            states = _SHIPMENT_STATES

        if active_ids:
            # validate some shipment data before to send carrier API
            for shipment in Shipment.browse(active_ids):
                if shipment.state not in states:
                    raise UserError(gettext(
                            'carrier_send_shipments.msg_shipment_state',
                            shipment=shipment.number,
                            state=shipment.state,
                            states=', '.join(states)))
                if not shipment.carrier:
                    raise UserError(gettext(
                            'carrier_send_shipments.msg_add_carrier',
                            shipment=shipment.number))
                if shipment.carrier_tracking_ref:
                    raise UserError(gettext(
                            'carrier_send_shipments.msg_shipment_sended',
                            shipment=shipment.number))
                if not shipment.carrier.apis:
                    raise UserError(gettext(
                            'carrier_send_shipments.msg_not_carrier_api',
                            name=shipment.carrier.rec_name))
                api, = shipment.carrier.apis
                if api.zips:
                    zips = api.zips.split(',')
                    if (shipment.delivery_address.zip
                            and shipment.delivery_address.zip in zips):
                        raise UserError(gettext(
                                'carrier_send_shipments.msg_shipment_zip',
                                shipment=shipment.number,
                                zip=shipment.delivery_address.zip))

        default = {}
        if active_model == 'stock.shipment.out.return':
            default['shipment_returns'] = active_ids
        else:
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
                    raise UserError(gettext(
                            'carrier_send_shipments.'
                            'msg_shipment_not_tracking_ref',
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
            if not shipment.carrier:
                continue
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


class LabelReport(Report):
    __name__ = 'stock.shipment.out.label.report'

    @classmethod
    def __setup__(cls):
        super(LabelReport, cls).__setup__()
        cls.__rpc__['execute'] = RPC(False)

    @classmethod
    def execute(cls, ids, data):
        pool = Pool()
        Shipment = pool.get('stock.shipment.out')
        API = pool.get('carrier.api')
        ActionReport = pool.get('ir.action.report')
        cls.check_access()

        if not ids or len(ids) != 1:
            raise UserError(
                    gettext('carrier_send_shipments.msg_several_shipments'))

        action_id = data.get('action_id')
        if action_id is None:
            action_reports = ActionReport.search([
                    ('report_name', '=', cls.__name__)
                    ])
            assert action_reports, '%s not found' % cls
            action_report = action_reports[0]
        else:
            action_report = ActionReport(action_id)

        shipment = Shipment(ids[0])
        if not shipment.carrier:
            return

        carrier_apis = API.search([
            ('carriers', 'in', [shipment.carrier.id]),
            ], limit=1)
        if not carrier_apis:
            return

        api, = carrier_apis
        if not api.print_report:
            return

        filename = slugify('%s-%s' % (api.method, action_report.name)).lower()

        if not shipment.carrier_tracking_label:
            if not hasattr(Shipment, 'get_labels_%s' % api.method):
                return

            print_label = getattr(Shipment, 'get_labels_%s' % api.method)
            labels = print_label(api, [shipment])
            if not labels:
                return
            label = labels[0]
        else:
            label = shipment.carrier_tracking_label

        Model = 'printer'
        Printer = None
        try:
            Printer = pool.get(Model)
        except KeyError:
            logger.warning('Redirect model "%s" not found.', Model)

        if Printer:
            return Printer.send_report(api.print_report, bytearray(label),
                filename, action_report)

        return (api.print_report, bytearray(label), action_report.direct_print,
            filename)
