import subprocess
import os
import simplejson

def render(source=None, filename=None, **kw):

    if filename is not None:
        tpl = filename
    elif source is not None:
        print source
        tpl = os.tempnam(None, "phantom")
        tpl_f = open(tpl, 'w')
        tpl_f.write(source)
        tpl_f.close()


    param = os.tempnam(None, "phantom")
    param += ".js"

    paramsdump = open(param, 'w')
    paramsdump.write("var param = ")
    simplejson.dump(kw, paramsdump)
    paramsdump.close()


    pipe = subprocess.Popen([
        "phantomjs",
        "phantom/render.js",
        tpl,
        param,],
        stdout=subprocess.PIPE,
    )
    out, _err = pipe.communicate()
    os.unlink(param)

    if filename is None:
        os.unlink(tpl)

    return out.strip()

def render_str(src, **kw):
    from jinja2.parser import Parser
    from jinja2.environment import Environment
    from genjs import JsGenerator
    env = Environment()
    parsed = Parser(env, src)
    gen = JsGenerator(env, '<internal>', '<internal>')
    gen.visit(parsed.parse())

    return render(source=gen.stream.getvalue(), **kw)

class Tpl(object):
    def __init__(self, source):
        self.source = source

    def render(self, kw=None, **kwargs):
        kw = kw or kwargs or {}
        ret = render_str(self.source, **kw)
        print ret
        return ret

if __name__ == '__main__':

    src = "<body>{% for x in mlist %}{{x}}{%endfor%}</body>"
    from jinja2.environment import Environment
    Environment.from_string = Tpl

    from nose.core import TestProgram
    TestProgram()#defaultTest='jinja2.testsuite.core_tags')

