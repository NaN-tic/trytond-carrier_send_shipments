#This file is part carrier_send_shipments module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.
from trytond.pool import Pool
from . import shipment
from . import sale
from . import manifest


def register():
    Pool.register(
        shipment.Configuration,
        shipment.ShipmentOut,
        shipment.CarrierSendShipmentsStart,
        shipment.CarrierSendShipmentsResult,
        shipment.CarrierPrintShipmentStart,
        shipment.CarrierPrintShipmentResult,
        sale.Sale,
        manifest.CarrierManifestStart,
        manifest.CarrierEnterManifest,
        shipment.CarrierGetLabelStart,
        shipment.CarrierGetLabelResult,
        module='carrier_send_shipments', type_='model')
    Pool.register(
        shipment.CarrierSendShipments,
        shipment.CarrierPrintShipment,
        manifest.CarrierManifest,
        shipment.CarrierGetLabel,
        module='carrier_send_shipments', type_='wizard')
