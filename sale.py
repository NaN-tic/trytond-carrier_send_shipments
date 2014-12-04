# This file is part of the carrier_send_shipments module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import PoolMeta

__all__ = ['Sale']
__metaclass__ = PoolMeta


class Sale:
    __name__ = 'sale.sale'

    def create_shipment(self, shipment_type):
        shipments = super(Sale, self).create_shipment(shipment_type)
        if not shipments:
            return
        service = self.carrier and self.carrier.service or False
        if shipment_type == 'out' and service:
            for shipment in shipments:
                shipment.carrier_service = service
                shipment.save()
        return shipments
