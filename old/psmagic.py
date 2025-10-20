
'''
I worked very hard some months ago to solve this problem as generally as possible.
Shown below are special cases of my results for languages without suffix operators.

Each unit of an expression is assigned a mask from 1 to 8 depending on whether it...
   8: is a term such as foo(1,2).bar[3]
   4: an infix such as /
   2: a prefix such as NOT
   1: a suffix
   3,5,6,7: a combination of the above based on their binary reading (5 = 4 | 1; literally 4 or 1)
'''

def decide_kinds(keys: list[int]) -> tuple[bool, list[int]]:
    if not keys: # an empty list is considered contradictory
        return (True, [])
    keys = list(keys)
    if keys[0] == 6:
        keys[0] = 2
    i = len(keys)-2
    contradiction = (keys[0] == 4) or (keys[-1] != 8) or (0 in keys)
    while i >= 0 and not contradiction:
        if keys[i] == 8:
            if keys[i+1] & 4:
                keys[i+1] = 4
            else:
                contradiction = True
        else:
            if keys[i+1] == 6:
                keys[i+1] = 2
            elif keys[i+1] == 4:
                contradiction = True
        i -= 1
    return (contradiction, keys)

def magic_parse_tree(terms, infixes, prefixes, infix_function, prefix_function) -> list:
    '''
    implementation of the special case of the general TIPS algorithm with no suffixes
    in this case we have two classes:
        8. term
        x=2,4,6. infix|prefix (infix, prefix, or ambiguous)
    the pattern "8 x" requires that the right be an infix
    the pattern "x x" requires that the right be a prefix
    the pattern "x EOF" requires that the left be a suffix, which is a contradiction
    additionally, if there are any terms which can't be anything, a contradiction is found
    '''
    if not terms:
        return None
    keys: list[int] = []
    for term in terms:
        if not isinstance(term, str):
            keys.append(8)
        else:
            keys.append((4 if term in infixes else 0) | (2 if term in prefixes else 0))
    contradiction, keys = decide_kinds(keys)
    if contradiction:
        return {"type": "err", "message":"term-infix-prefix resolution failed", "argument":terms, "keys":keys}
    # use the keys to determine which precedence values to use for each term or operator
    TP: tuple[int, int] = (-1, -1) # "term priority"
    priorities: list[tuple[int, int]] = []
    for i, key in enumerate(keys):
        term = terms[i]
        match key:
            case 8:
                priorities.append(TP)
            case 4:
                priorities.append(infixes[term])
            case 2:
                priorities.append((-1, prefixes[term]))
    '''
    logically, this makes sense. A prefix (viewed from the left side) should look like an opaque term
    Until or unless the prefix is merged, it is completely immune to all leftward merges.
    From the right side, a prefix should look indistinguishable from a (term infix) pair:
    Under no circumstance can an infix to the left of a prefix impact the precedence of anything occurring to the right
    ... until the prefix has been merged away, revealing the infix to the righter world.
    '''
    # TASK: given the grammar (2* 8) (4 (2* 8))*, resolve this into a tree by merging according to pratt-like rules
    terms = list(terms) # list mutability will now be abused in a recursive function algorithm
    def pop(index: int):
        priorities.pop(index)
        return terms.pop(index)
    def associate(index: int, binding: int, argument: bool):
        '''
        TASK: guarantee that term[INDEX] is the maximal consolidated expression with binding not weaker than BINDING
        this function CAN benefit greatly from tail-call optimization, only the input variables are needed after each recursive call
        argument: position (index-1) contains a consolidated term
        binding: precedence impact from the left
            if argument: this impact is from (index-2)
            else: this impact is from (index-1)
        '''
        if index >= len(terms):
            return
        left_bind, right_bind = priorities[index]
        if left_bind == -1:
            if right_bind != -1: # prefix
                associate(index+1, right_bind, False)
                z = pop(index+1)
                terms[index] = prefix_function(terms[index], z)
                priorities[index] = TP
            # whether a prefix was found or not, terms[index] is now a term and not a prefix.
            associate(index+1, binding, True)
        elif binding < left_bind and argument:
            '''
            as an aside, this is the sole reason lefts & rights cannot be equal:
                to prevent any imagination of handling <= DIFFERENTLY to <;
                to prevent all "off by one" errors and to make fully explicit the left or right associativity of all operators.
            '''
            # we are looking at an operator AND the precedence impact of the next left operator is weaker than this operator
            associate(index+1, right_bind, False) # per the TASK: guarantee the right argument is maximal yet valid
            z = pop(index+1) # this is safe because every [4] in keys is eventually flanked by terms
            y = pop(index)
            terms[index-1] = infix_function(y, terms[index-1], z)
            associate(index-1, binding, argument) # after producing this infix expression, regress and review.
    associate(0, -1, False)
    if len(terms) != 1:
        return {"type": "err", "message": "association error: algorithm failed to resolve terms and operators into a single tree",
                "argument": terms}
    return terms[0]
