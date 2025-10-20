from typing import Iterator

'''
tokens provided:
    name, num, str, op
'''

TOKEN = tuple[str, str]
PREFERRED_QUOTE = "\""
HEX = "0123456789ABCDEF"
ESCAPE_MAP = {
    "a": "\a", "b": "\b", "n": "\n", "r": "\r", "s": " ", "t": "\t",
    "\"": "\"", "'": "'", "\\": "\\"
}

# TODO: put the INDENT/DEDENT rules back in
# TODO: ^ medi-processer to make a newline exception inside () [] and after ,

def sort_dict(old: dict) -> dict:
    new = {}
    for key in reversed(sorted(list(old))):
        new[key] = old[key]
    return new

SPECIAL_SYMBOLS = sort_dict({
    2:set("<= >= <>".split()),
    1:set("~/%^&*()-=+[]{}<>,.;:")})
SPECIAL_KEYS = dict((j, "op") for j in "<= >= <> < > ~ / % ^ & * - +".split())
SPECIALER_KEYS = set(i for v in SPECIAL_SYMBOLS.values() for i in v if i not in SPECIAL_KEYS)

OPENERS = set("({[")
CLOSERS = set("]})")

def lex(src: str, keywords: set[str], keyops: set[str]) -> Iterator[TOKEN]:
    _Q = PREFERRED_QUOTE
    _SPECIAL_KEYS = SPECIAL_KEYS
    _SPECIAL_SYMBOLS = SPECIAL_SYMBOLS
    _OPENERS = OPENERS
    _CLOSERS = CLOSERS
    _NEWLINE = ("\n", "\n")
    _INDENT = ("indent", " ")
    _DEDENT = ("dedent", " ")
    parens = 0
    index = 0
    indent = [""]
    recent_ws = ""
    recent_nl = False
    while index < len(src):
        previous = index
        index = discard_comments(src, index)
        if index != previous:
            continue
        index, _ = pop_newline(src, index)
        if index != previous:
            recent_nl = parens == 0
            recent_ws = ""
            continue
        index, ws = pop_whitespace(src, index)
        if index != previous:
            recent_ws = ws
            continue
        if recent_nl:
            while True:
                ind = indent[-1]
                if ind == recent_ws:
                    yield _NEWLINE
                    break
                elif recent_ws.startswith(ind):
                    indent.append(recent_ws)
                    yield _INDENT
                    break
                elif not ind.startswith(recent_ws):
                    raise IndentationError(f"incompatible dedent detected from {repr(ind)} to {repr(recent_ws)}")
                indent.pop()
                yield _DEDENT
            recent_nl = False
        c = src[index]
        if 'a' <= c.lower() <= 'z' or c == "_":
            index, token = pop_name(src, index)
            if token in keyops:
                yield ("op", token)
            elif token in keywords:
                yield (token, token)
            elif token in {"true", "false"}:
                yield ("literal_bool", token)
            else:
                yield ("name", token)
            continue
        if '0' <= c <= '9' or c == '.':
            index, token, err = pop_num(src, index)
            if err:
                raise SyntaxError(f"{err} while parsing number at {previous}:{index}")
            yield ("." if token == "." else "literal_num" if "." not in token else "literal_float", token)
            continue
        if c == _Q:
            index, token, err = pop_string(src, index)
            if err:
                raise SyntaxError(f"{err} while parsing string at {previous}:{index}")
            yield ("literal_string", token)
            continue
        for length, symbol_set in _SPECIAL_SYMBOLS.items():
            substring = src[index:index+length]
            if substring in symbol_set:
                if substring in _OPENERS:
                    parens += 1
                elif substring in _CLOSERS:
                    parens -= 1
                index += length
                yield (_SPECIAL_KEYS.get(substring, substring), substring)
                break
        else:
            raise SyntaxError(f"unexpected char at {index}: {repr(src[index:index+20])}")
    yield ("EOF", "")

def discard_comments(src: str, index: int) -> int:
    if src[index:index+2] == "//":
        index, _ = pop_comment(src, index)
    return index

def pop_utility(src: str, index: int, decider) -> tuple[int, str]:
    start = index
    while (c := src[index:index+1]) and decider(c):
        index += 1
    return (index, src[start:index])

# below are the dumb pop functions

def pop_newline(src: str, index: int) -> tuple[int, str]:
    index, r = pop_utility(src, index, "\n\r".__contains__)
    return index, ("\n" if r else "")

def pop_whitespace(src: str, index: int) -> tuple[int, str]:
    return pop_utility(src, index, " \t".__contains__)

def pop_name(src: str, index: int) -> tuple[int, str]:
    return pop_utility(src, index, str.isalnum)

def pop_num(src: str, index: int) -> tuple[int, str, str]:
    # this function could be expanded to support hex (0xABC) values
    index, num = pop_utility(src, index, "0123456789".__contains__)
    if src[index:index+1] == ".":
        index, fraction = pop_utility(src, index+1, "0123456789".__contains__)
        num += "." + fraction
        if src[index:index+1] == ".":
            return index, num, "multiple dots detected"
    return index, num, ""

# all of the below functions presume an entry condition has been met to guarantee the first char is relevant and correct

def pop_comment(src: str, index: int) -> tuple[int, str]:
    # intentionally exclude the \n which ends the comment
    end = src.find("\n", index+2)
    if end == -1:
        end = len(src)
    return end, src[index:end]

def pop_string(src: str, index: int) -> tuple[int, str, str]:
    # in this function, early returns are used in place of raising exceptions
    _ESCAPE_MAP = ESCAPE_MAP
    _HEX = HEX
    _Q = PREFERRED_QUOTE
    result = _Q
    index += 1
    while (c := src[index:index+1]) not in _Q:
        index += 1
        if c != "\\":
            result += c
            continue
        c = src[index:index+1]
        if not c:
            return (index, result, "cannot escape EOF")
        index += 1
        if c != "x":
            result += _ESCAPE_MAP.get(c, c)
            continue
        pair = src[index:index+2].upper()
        if len(pair) < 2:
            break
        if pair[0] not in _HEX or pair[1] not in _HEX:
            return (index, result, "invalid hex sequence")
    if not c:
        return (index, result, "EOF")
    index += 1
    result += c
    return (index, result, "")
