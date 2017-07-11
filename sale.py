# This file is part of the carrier_send_shipments module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import PoolMeta

__all__ = ['Sale']


class Sale:
    __metaclass__ = PoolMeta
    __name__ = 'sale.sale'

    def _get_shipment_sale(self, Shipment, key):
        shipment = super(Sale, self)._get_shipment_sale(Shipment, key)
        if Shipment.__name__ == 'stock.shipment.out':
            if self.carrier and self.carrier.service:
                shipment.carrier_service = self.carrier.service

            address = shipment.customer.address_get(type='delivery')
            if address.comment_shipment:
                shipment.carrier_notes = shipment._comment2txt(
                        address.comment_shipment)
            elif shipment.customer.comment_shipment:
                shipment.carrier_notes = shipment._comment2txt(
                        shipment.customer.comment_shipment)

        return shipment
