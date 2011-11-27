import subprocess
import os
import simplejson
import re

from jinja2.parser import Parser
from genjs import JsGenerator

def render(source=None, filename=None, **kw):

    if filename is not None:
        tpl = filename
    elif source is not None:
        tpl = os.tempnam(None, "phantom")
        tpl_f = open(tpl, 'w')
        tpl_f.write(source)
        tpl_f.close()


    for k,v in kw.items():
        if hasattr(v,'next'):
            kw[k] = list(v)

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

    rep = {
            "true": "True",
            "false": "False",
    }
    ret = out[:-1]
    for k,v in rep.items():
        ret = ret.replace(k,v)

    re_fix = [
        (r"\[(\w+), (\w+)\]", r"('\1', \2)"),
    ]
    for pt,rp in re_fix:
        ret = re.sub(pt, rp, ret)

    return ret

def render_str(src, **kw):
    from jinja2.environment import Environment
    env = Environment()
    parsed = Parser(env, src)
    gen = JsGenerator(env, '<internal>', '<internal>')
    gen.visit(parsed.parse())

    return render(source=gen.stream.getvalue(), **kw)

class Tpl(object):
    def __init__(self, env, source=None, name=None):
        self.env = env
        self.js = {}
        if source:
            self.js[name] = self.js_compile(source, name)

        tpls = env.loader.list_templates() if env.loader else []
        for _name in tpls:

            _source,_,_ = env.loader.get_source(env, _name)
            self.js[_name] = self.js_compile(_source, _name)

        self.name = name

    def js_compile(self, source, name):
        code = Parser(self.env, source)
        gen = JsGenerator(self.env, name, name)
        gen.visit(code.parse())
        return gen.stream.getvalue()

    def js_all(self):
        return str.join("\n", self.js.values())

    def render(self, kw=None, **kwargs):
        kw = kw or kwargs or {}
        print self.js_all()
        ret = render(self.js_all(), _entry=self.name, **kw)
        print ret
        return ret

if __name__ == '__main__':

    src = "<body>{% for x in mlist %}{{x}}{%endfor%}</body>"
    from jinja2 import environment
    import jinja2
    class FakeEnv(environment.Environment):
        def get_template(self, name):
            return Tpl(self, name=name)

        def from_string(self, source):
            tpl = Tpl(self, source, 'main')
            return tpl

    environment.Environment = FakeEnv
    jinja2.Environment = FakeEnv

    from nose.core import TestProgram
    TestProgram()#defaultTest='jinja2.testsuite.core_tags')

