"""
OpenPyXl_Utils

Utility functions to help with OpenPyXL.

Author: Len Wanger
Date: 7/28/2016
"""

"""
Routine to calculate the value of a formula in an openpyxl cell.

TODO:
- add more formulas... currently only supports sum, average, min and max
- can't deal with cell references on other sheets
- ranges can't have commas or spaces
- can't handle named ranges
- can't detect/handle circular references

Author: Len Wanger
Date: 7/28/2016
"""

import numbers
import collections.abc
import logging
import openpyxl as xl
from openpyxl.formula import Tokenizer


infix_swap = {'^': '**', '=': '==', '<>': '!=', '&': '+'}
func_swap = {'ABS(': 'abs(', 'SUM(': 'sum(', 'MIN(': 'min(', 'MAX(': 'max(', 'AVERAGE(': 'average(', 'IF(': 'excel_if(',
             'AND(': 'excel_and(', 'OR(': 'excel_or('}
operand_swap = {'TRUE': 'True', 'FALSE': 'False'}


#
# OpenPyXl utility functions
#
def sheet_generator(wb, ignore_sheets=None):
    if ignore_sheets is None:
        ignore_sheets = []
    sheets = wb.get_sheet_names()

    for sheet in sheets:
        sh = wb.get_sheet_by_name(sheet)

        if sh.title in ignore_sheets:
            logging.warning('\t{:15}Ignoring sheet'.format(sh.title))
            continue

        yield sh


def make_cell_range(sh, min_col='A', max_col=None, min_row=1, max_row=None):
    if max_col is None:
        max_col = sh.max_col
    if max_row is None:
        max_row = sh.max_row

    return '{}{}:{}{}'.format(min_col, min_row, max_col, max_row)


def is_blank_cell(cell):
    if cell.value is None:
        return True
    elif isinstance(cell.value, str) and (len(cell.value) == 0 or cell.value.isspace()):
        return True
    else:
        return False


def is_formula(cell):  # cell.type == 'f' is a formula?
    if cell.value and isinstance(cell.value, str) and cell.value[0] == '=':
        return True
    else:
        return False


def is_number(cell):  # LRW - should check for data_type of 'n' or 'f' instead?
    if cell.value is None:
        return False
    else:
        return isinstance(cell.value, numbers.Number)
        # return cell.data_type in ('n', 'f') and not cell.is_date # strings can be type 'f'


def is_date(cell):
    if cell.value is None:
        return False
    else:
        return cell.is_date


def is_string(cell):
    if cell.value is None:
        return False
    else:
        return cell.data_type == 's'


def startswith(cell, s, lower=True):
    if is_string(cell):
        if lower:
            return cell.value.lower().startswith(s)
        else:
            return cell.value.startswith(s)
    return False


def cell_range_generator(ws, cell_range, skip_nones=True):
    for row in ws.iter_rows(cell_range):
        for cell in row:
            if cell.value is None and skip_nones:
                continue
            yield cell



def get_cell_value(ws, cell, none_as_zero=True):
    """
    Returns: the cell value. If the cell contains a formula, the formula value is evaluated and returned
    """
    if cell.value is None:
        return 0 if none_as_zero else None
    if is_formula(cell):
        return eval_formula(ws, cell.value)
    else:
        return cell.value


def get_cell(ws, s, none_as_zero=True):
    """
    ws - openpyxl worksheet
    s - string for the cell location (e.g. 'C1') or range (e.g. 'B1:C12')
    Return the value for the cell. If s is a range, returns a tuple of the cell values.
    """
    if s.find(':') == -1:  # simple cell
        return get_cell_value(ws, ws[s], none_as_zero)
    else:  # it's a range
        skip_nones = not none_as_zero  # don't include None values in the tuple if none_as_zero is False
        return tuple(get_cell_value(ws, c, none_as_zero) for c in cell_range_generator(ws, s, skip_nones))


def average(*args):
    # Emulate the Excel average formula
    total = items = 0

    for arg in args:
        if isinstance(arg, numbers.Number):
            total += arg
            items += 1
        elif isinstance(arg, collections.abc.Iterable):
            total += sum(arg)
            items += len(arg)
        else:
            s = 'Average function cannot handle argument type ({})'.format(arg)
            logging.error(s)
            raise RuntimeError(s)

    return total/items


def excel_if(test, yes, no):
    # Emulate the Excel if statement
    return yes if test else no


def excel_and(*args):
    # Emulate the Excel and statement
    for arg in args:
        if not arg:
            return False
    return True


def excel_or(*args):
    # Emulate the Excel or statement
    for arg in args:
        if arg:
            return True
    return False


def eval_formula(ws, formula_str):
    eval_str = ''
    tok = Tokenizer(formula_str)
    tok.parse()
    #print("\n".join("%12s%11s%9s" % (t.value, t.type, t.subtype) for t in tok.items))

    for t in tok.items:
        if t.subtype == 'RANGE':
            range_str = 'get_cell(ws,"{}")'.format(t.value)
            eval_str += range_str
        elif t.type == 'OPERATOR-INFIX':
            try:
                eval_str += infix_swap[t.value]
            except KeyError:
                eval_str += t.value
        elif t.type == 'OPERAND':
            try:
                eval_str += operand_swap[t.value]
            except KeyError:
                eval_str += t.value
        elif t.type == 'FUNC' and t.subtype == 'OPEN':
            try:
                eval_str += func_swap[t.value]
            except KeyError:
                logging.error('Unsupported function in formula ({})'.format(t.value[:-1]))
                raise
        else:
            eval_str += t.value

    #print('formula_str=%s   eval_str=%s' % (formula_str, eval_str))
    # value = eval(eval_str)
    # return value
    if len(eval_str) == 0:
        pass

    try:
        return eval(eval_str)
    except:
        logging.error('Exception evaluating eval_str=\'{}\''.format(eval_str))
        raise


if __name__ == '__main__':
    infile = 'D:/SkyDrive/Documents/python/beancount/rlwi/formula_test.xlsx'
    cell_range = 'B3:B25'

    wb = xl.load_workbook(infile, read_only=True)
    sheets = wb.get_sheet_names()
    ws = wb.get_sheet_by_name(sheets[0])  # or use wb.active

    for row in ws.iter_rows(cell_range):
        for cell in row:
            if cell.data_type == 'f':
                try:
                    value = eval_formula(ws, cell.value)
                    print('Value returned from eval_formula ({}): {}'.format(cell.value, value))
                except KeyError as e:
                    print('Unknown formula or operand... ignoring cell (%s)' % cell.value)  # ignore unknown formula
            else:
                print(cell.value)

    print('done.')
