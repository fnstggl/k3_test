#!/usr/bin/env python3
"""Write a Param.cpp with selected user knobs changed, starting from the pristine git copy.

Usage: set_param.py <pristine_Param.cpp> <out_Param.cpp> key=value [key=value ...]

Only the FIRST assignment statement `key = ...;` in the file is rewritten (all user knobs
in V1.4 Param.cpp are first assigned in the "user defined design options" block at the
top of Param::Param()).  Exits non-zero if a key is not found, so typos cannot silently
leave a default in place.  Prints a one-line summary of every substitution.
"""
import re
import sys

src, dst, *kvs = sys.argv[1:]
text = open(src).read()
for kv in kvs:
    key, val = kv.split('=', 1)
    pat = re.compile(r'^([ \t]*)' + re.escape(key) + r'([ \t]*)=([ \t]*)([^;\n]*);', re.M)
    m = pat.search(text)
    if not m:
        sys.exit('set_param.py: knob %r not found in %s' % (key, src))
    line_no = text.count('\n', 0, m.start()) + 1
    old = m.group(4)
    text = text[:m.start()] + m.group(1) + key + m.group(2) + '=' + m.group(3) + val + ';' + text[m.end():]
    print('[set_param] Param.cpp:%d  %s = %s  ->  %s' % (line_no, key, old.strip(), val))
open(dst, 'w').write(text)
