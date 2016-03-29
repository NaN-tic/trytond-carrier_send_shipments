# This file is part of the carrier_send_shipments module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool, PoolMeta

__all__ = ['Sale']


class Sale:
    __metaclass__ = PoolMeta
    __name__ = 'sale.sale'

    def create_shipment(self, shipment_type):
        ShipmentOut = Pool().get('stock.shipment.out')

        shipments = super(Sale, self).create_shipment(shipment_type)
        if not shipments:
            return

        if shipment_type == 'out':
            to_save = []
            for shipment in shipments:
                if self.carrier and self.carrier.service:
                    shipment.carrier_service = self.carrier.service

                address = shipment.customer.address_get(type='delivery')
                if address.comment_shipment:
                    shipment.carrier_notes = shipment._comment2txt(
                            address.comment_shipment)
                elif shipment.customer.comment_shipment:
                    shipment.carrier_notes = shipment._comment2txt(
                            shipment.customer.comment_shipment)
                
                if shipment.carrier_service or shipment.carrier_notes:
                    to_save.append(shipment)

            if to_save:
                ShipmentOut.save(to_save)

        return shipments
