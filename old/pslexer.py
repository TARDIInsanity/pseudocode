from typing import Iterator

PREFERRED_QUOTE = "\""
HEX = "0123456789ABCDEF"
ESCAPE_MAP = {
    "a": "\a", "b": "\b", "n": "\n", "r": "\r", "s": " ", "t": "\t",
    "\"": "\"", "'": "'", "\\": "\\"
}

def sort_dict(old: dict) -> dict:
    new = {}
    for key in reversed(sorted(list(old))):
        new[key] = old[key]
    return new

SPECIAL_SYMBOLS = sort_dict({
    2:set("<= <> >= !=".split()),
    1:set("<>=+-*/()[]{}:,")})

def simple_preprocess(src: str) -> str:
    # useful when pasting code from a word processor which uses directional quotes
    return src.replace("“", PREFERRED_QUOTE).replace("”", PREFERRED_QUOTE)

def lex(src: str) -> Iterator[str]:
    _Q = PREFERRED_QUOTE
    _SPECIAL_SYMBOLS = SPECIAL_SYMBOLS
    index = 0
    while index < len(src):
        previous = index
        index = discard_comments(src, index)
        if index != previous:
            continue
        c = src[index]
        if 'a' <= c.lower() <= 'z':
            index, token = pop_name(src, index)
            yield token
            continue
        if '0' <= c <= '9' or c == '.':
            index, token, err = pop_num(src, index)
            if err:
                raise SyntaxError(f"{err} while parsing number at {previous}:{index}")
            yield token
            continue
        if c == _Q:
            index, token, err = pop_string(src, index)
            if err:
                raise SyntaxError(f"{err} while parsing string at {previous}:{index}")
            yield token
            continue
        for length, symbol_set in _SPECIAL_SYMBOLS.items():
            substring = src[index:index+length]
            if substring in symbol_set:
                index += length
                yield substring
                break

def newline_lex(src: str) -> Iterator[str]:
    '''
    Officially, formally, speaking: this is not a proper lexer.
    This is a hybrid program which performs all the duties
    of a lexer with the slightest additional processing, namely:
    reduced emission of line breaks.
    '''
    _Q = PREFERRED_QUOTE
    _SPECIAL_SYMBOLS = SPECIAL_SYMBOLS
    index = 0
    newline = False
    while index < len(src):
        if src[index:index+2] == "//":
            index, _ = pop_comment(src, index)
            continue
        previous = index
        c = src[index]
        if c in " \t":
            index, _ = pop_whitespace(src, index)
            continue
        if c in "\n\r":
            newline = True
            index, _ = pop_newline(src, index)
            continue
        if newline:
            yield "\n"
            newline = False
        if 'a' <= c.lower() <= 'z':
            index, token = pop_name(src, index)
            yield token
            continue
        if '0' <= c <= '9' or c == '.':
            index, token, err = pop_num(src, index)
            if err:
                raise SyntaxError(f"{err} while parsing number at {previous}:{index}")
            yield token
            continue
        if c == _Q:
            index, token, err = pop_string(src, index)
            if err:
                raise SyntaxError(f"{err} while parsing string at {previous}:{index}")
            yield token
            continue
        for length, symbol_set in _SPECIAL_SYMBOLS.items():
            substring = src[index:index+length]
            if substring in symbol_set:
                index += length
                yield substring
                break
        else:
            print("invalid chars beginning at {index}: "+src[index:index+10])
            break

def pop_utility(src: str, index: int, decider) -> tuple[int, str]:
    start = index
    while (c := src[index:index+1]) and decider(c):
        index += 1
    return (index, src[start:index])

def discard_comments(src: str, index: int) -> int:
    index, _ = pop_utility(src, index, " \t\n\r".__contains__)
    while src[index:index+2] == "//":
        index, _ = pop_comment(src, index)
        index, _ = pop_utility(src, index, " \t\n\r".__contains__)
    return index

# all of the below functions presume an entry condition has been met to guarantee the first char is relevant and correct

def pop_newline(src: str, index: int) -> tuple[int, str]:
    return pop_utility(src, index, "\n\r".__contains__)

def pop_whitespace(src: str, index: int) -> tuple[int, str]:
    return pop_utility(src, index, " \t".__contains__)

def pop_comment(src: str, index: int) -> tuple[int, str]:
    # intentionally exclude the \n which ends the comment
    end = src.find("\n", index+2)
    if end == -1:
        end = len(src)
    return end, src[index:end]

def pop_name(src: str, index: int) -> tuple[int, str]:
    return pop_utility(src, index, str.isalnum)

def pop_num(src: str, index: int) -> tuple[int, str, str]:
    # this function could be expanded to support hex (0xABC) values
    index, num = pop_utility(src, index, "0123456789".__contains__)
    if src[index:index+1] == ".":
        index, fraction = pop_utility(src, index+1, "0123456789".__contains__)
        num += "." + fraction
    return index, num, ""

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
        index += 1
        if not c:
            break
        if c != "x":
            result += _ESCAPE_MAP.get(c, c)
            continue
        pair = src[index:index+2].upper()
        if len(pair) < 2:
            return (index, result, "EOF")
        if pair[0] not in _HEX or pair[1] not in _HEX:
            return (index, result, "invalid hex sequence")
    if not c:
        return (index, result, "EOF")
    index += 1
    result += c
    return (index, result, "")
