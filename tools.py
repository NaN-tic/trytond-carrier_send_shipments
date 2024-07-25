# encoding: utf-8
# This file is part of the carrier_send_shipments module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import unicodedata

SRC_CHARS = u"""/*+?¿!&$[]{}`^<>=~%|\\"""

def unaccent(text):
    if not text:
        return ''
    for c in range(len(SRC_CHARS)):
        text = text.replace(SRC_CHARS[c], '')
    text = text.replace('º', '. ')
    text = text.replace('ª', '. ')
    text = text.replace('  ', ' ')
    output = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore')
    return output.decode('utf-8')

def unspaces(text):
    if text:
        return text.replace(" ", "")
    return ''

def split_into_blocks(text, max_length=100):
    words = text.split()
    blocks = []
    current_block = ""

    for word in words:
        # Check if adding the next word would exceed the max_length
        if len(current_block) + len(word) + 1 <= max_length:
            if current_block:
                current_block += " " + word
            else:
                current_block = word
        else:
            # If the current block is full, store it and start a new one
            blocks.append(current_block)
            current_block = word

    # Add the last block
    blocks.append(current_block)

    # Handle any remaining words for the last block, making sure it doesn'
    # exceed max_length characters
    remaining_words = " ".join(words[len(" ".join(blocks).split()):])
    if remaining_words and len(remaining_words) <= max_length:
        blocks.append(remaining_words)

    return blocks
