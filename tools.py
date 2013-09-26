# encoding: utf-8
#This file is part carrier_send_shipments module for Tryton.
#The COPYRIGHT file at the top level of this repository contains 
#the full copyright notices and license terms.
import unicodedata

SRC_CHARS = u"""'"()/*-+?¿!&$[]{}@#`'^:;<>=~%,|\\ºª"""

def unaccent(text):
    if not (isinstance(text, str) or isinstance(text, unicode)):
        return str(text)
    if isinstance(text, str):
        text = unicode(text, 'utf-8')
    text = text.lower()
    for c in xrange(len(SRC_CHARS)):
        text = text.replace(SRC_CHARS[c], '')
    return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore')
