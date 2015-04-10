#This file is part carrier_send_shipments module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.
from trytond.pool import Pool
from .shipment import *
from .sale import *
from .manifest import *


def register():
    Pool.register(
        Configuration,
        ShipmentOut,
        CarrierSendShipmentsStart,
        CarrierSendShipmentsResult,
        CarrierPrintShipmentStart,
        CarrierPrintShipmentResult,
        Sale,
        CarrierManifestStart,
        CarrierEnterManifest,
        CarrierGetLabelStart,
        CarrierGetLabelResult,
        module='carrier_send_shipments', type_='model')
    Pool.register(
        CarrierSendShipments,
        CarrierPrintShipment,
        CarrierManifest,
        CarrierGetLabel,
        module='carrier_send_shipments', type_='wizard')
