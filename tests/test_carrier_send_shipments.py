#!/usr/bin/env python
#This file is part carrier_send_shipments module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.

import sys
import os
DIR = os.path.abspath(os.path.normpath(os.path.join(__file__,
    '..', '..', '..', '..', '..', 'trytond')))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))

import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import test_view, test_depends


class CarrierSendShipmentsTestCase(unittest.TestCase):
    '''
    Test Carrier Send Shipments module.
    '''

    def setUp(self):
        trytond.tests.test_tryton.install_module('carrier_send_shipments')

    def test0005views(self):
        '''
        Test views.
        '''
        test_view('carrier_send_shipments')

    def test0006depends(self):
        '''
        Test depends.
        '''
        test_depends()


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
        CarrierSendShipmentsTestCase))
    return suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
