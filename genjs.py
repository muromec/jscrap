from __future__ import print_function

from jinja2 import Environment, FileSystemLoader, ModuleLoader
from jinja2 import compiler
from jinja2.compiler import Frame, find_undeclared, CompilerExit

from jinja2 import nodes
from jinja2.nodes import EvalContext
from jinja2.utils import Markup, concat, escape, is_python_keyword, next

from functools import wraps

def fname(cls, s):
    return s.replace(".html", '')+".js"



def wrap(f):
    @wraps(f)
    def wrapped(*a, **kw):
        print("called %s" % f.__name__)

        return f(*a, **kw)
    return wrapped

WHITE = [
        "writeline",
        "newline",
        "write",
        "indent",
]

for attr_name in dir(compiler.CodeGenerator):
    if attr_name in WHITE:
        continue

    attr = getattr(compiler.CodeGenerator, attr_name)
    if not hasattr(attr, 'im_func'):
        continue

    setattr(compiler.CodeGenerator, attr_name, wrap(attr))

def jbool(val):
    return "true" if val else "false"

class JsGenerator(compiler.CodeGenerator):
    def visit_Template(self, node, frame=None):
        eval_ctx = EvalContext(self.environment, self.name)

        # find all blocks
        for block in node.find_all(nodes.Block):
            if block.name in self.blocks:
                self.fail('block %r defined twice' % block.name, block.lineno)
            self.blocks[block.name] = block

        for import_ in node.find_all(nodes.ImportedName):
            assert False, "imports not supported"

        self.writeline('var name = %r;' % self.name)

        self.writeline('var root = function(context)', extra=1)

        # process the root
        frame = Frame(eval_ctx)
        frame.inspect(node.body)
        frame.toplevel = frame.rootlevel = True
        frame.require_output_check =  not self.has_known_extends
        self.indent()
            
        self.writeline('var parent_template = null;')

        if 'self' in find_undeclared(node.body, ('self',)):
            assert False, "dont know self magic"

        self.buffer(frame)
        self.pull_locals(frame)
        self.pull_dependencies(node.body)
        self.blockvisit(node.body, frame)
        self.return_buffer_contents(frame)
        self.outdent()

        """
        if not self.has_known_extends:
            self.indent()
            self.writeline('if parent_template is not None:')
        self.indent()
        self.writeline('for event in parent_template.'
                       'root_render_func(context):')
        self.indent()
        self.writeline('yield event')
        self.outdent(2 + (not self.has_known_extends))
        """

        # at this point we now have the blocks collected and can visit them too.
        for name, block in self.blocks.iteritems():
            block_frame = Frame(eval_ctx)
            block_frame.inspect(block.body)
            block_frame.block = name
            block_frame.buffer = frame.buffer
            self.writeline('var block_%s = function(context, %s)' % (name, frame.buffer),
                           block, 1)
            self.indent()
            undeclared = find_undeclared(block.body, ('self', 'super'))
            if 'self' in undeclared:
                block_frame.identifiers.add_special('self')
                self.writeline('l_self = TemplateReference(context)')
            if 'super' in undeclared:
                block_frame.identifiers.add_special('super')
                self.writeline('l_super = context.super(%r, '
                               'block_%s)' % (name, name))
            self.pull_locals(block_frame)
            self.pull_dependencies(block.body)
            self.blockvisit(block.body, block_frame)
            self.outdent()

        self.writeline('blocks = {%s}' % ', '.join('%r: block_%s' % (x, x)
                                                   for x in self.blocks),
                       extra=1)


    def visit_Block(self, node, frame):
        """Call a block and register it for the template."""
        level = 1
        if frame.toplevel:
            # if we know that we are a child template, there is no need to
            # check if we are one
            if self.has_known_extends:
                return
            if self.extends_so_far > 0:
                self.writeline('if parent_template is None:')
                self.indent()
                level += 1
        context = node.scoped and 'context.derived(locals())' or 'context'
        self.writeline('blocks[%r](%s, %s)' % (
                       node.name, context, frame.buffer), node)


    def blockvisit(self, nodes, frame):
        """Visit a list of nodes as block in a frame.  If the current frame
        is no buffer a dummy ``if 0: yield None`` is written automatically
        unless the force_generator parameter is set to False.
        """
        self.writeline('true;')
        try:
            for node in nodes:
                self.visit(node, frame)
        except CompilerExit:
            pass

    def indent(self,):
        self.write("{")
        self._indentation += 1

    def outdent(self, step=1):
        """Outdent by step."""
        self._indentation -= step
        self.writeline("}"*step)

    def return_buffer_contents(self, frame):
        self.writeline('return %s.join("");' % frame.buffer)


    def buffer(self, frame):
        frame.buffer = self.temporary_identifier()
        self.writeline('var %s = [];' % frame.buffer);

    def pull_locals(self, frame):
        """Pull all the references identifiers into the local scope."""
        for name in frame.identifiers.undeclared:
            self.writeline('var l_%s = context.resolve(%r)' % (name, name))

    def push_scope(self, frame, extra_vars=()):
        """This function returns all the shadowed variables in a dict
        in the form name: alias and will write the required assignments
        into the current scope.  No indentation takes place.

        This also predefines locally declared variables from the loop
        body because under some circumstances it may be the case that

        `extra_vars` is passed to `Frame.find_shadowed`.
        """
        aliases = {}
        for name in frame.find_shadowed(extra_vars):
            aliases[name] = ident = self.temporary_identifier()
            self.writeline('var %s = l_%s;' % (ident, name))
        to_declare = set()
        for name in frame.identifiers.declared_locally:
            if name not in aliases:
                to_declare.add('l_' + name)
        if to_declare:
            self.writeline('var '+(' = '.join(to_declare)) + ' = undefined;')
        return aliases

    def pop_scope(self, aliases, frame):
        """Restore all aliases and delete unused variables."""
        for name, alias in aliases.iteritems():
            self.writeline('var l_%s = %s;' % (name, alias))
        to_delete = set()
        for name in frame.identifiers.declared_locally:
            if name not in aliases:
                to_delete.add('l_' + name)
        if to_delete:
            # we cannot use the del statement here because enclosed
            # scopes can trigger a SyntaxError:
            #   a = 42; b = lambda: a; del a
            self.writeline('var '+(' = '.join(to_delete)) + ' = undefined;')

 
 
    def visit_Output(self, node, frame):
        # if we have a known extends statement, we don't output anything
        # if we are in a require_output_check section
        if self.has_known_extends and frame.require_output_check:
            return

        if self.environment.finalize:
            finalize = lambda x: unicode(self.environment.finalize(x))
        else:
            finalize = unicode

        # if we are inside a frame that requires output checking, we do so
        outdent_later = False
        if frame.require_output_check:
            self.writeline('if(parent_template === null)')
            self.indent()
            outdent_later = True

        # try to evaluate as many chunks as possible into a static
        # string at compile time.
        body = []
        for child in node.nodes:
            try:
                const = child.as_const(frame.eval_ctx)
            except nodes.Impossible:
                body.append(child)
                continue
            # the frame can't be volatile here, becaus otherwise the
            # as_const() function would raise an Impossible exception
            # at that point.
            try:
                if frame.eval_ctx.autoescape:
                    if hasattr(const, '__html__'):
                        const = const.__html__()
                    else:
                        const = escape(const)
                const = finalize(const)
            except Exception:
                # if something goes wrong here we evaluate the node
                # at runtime for easier debugging
                body.append(child)
                continue
            if body and isinstance(body[-1], list):
                body[-1].append(const)
            else:
                body.append([const])

        for item in body:
            if isinstance(item, list):
                val = str(concat(item))
                val = val.replace("\n", "\\\n")
                self.writeline('%s.push("%s");' % (
                    frame.buffer, val)
                )

            else:
                self.writeline('%s.push(' % frame.buffer, item)
                self.visit(item, frame)
                self.write(');')

        if outdent_later:
            self.outdent()

    def visit_Getattr(self, node, frame):
        self.visit(node.node, frame)
        self.write('[%r]' % node.attr)


    def visit_For(self, node, frame):
        # when calculating the nodes for the inner frame we have to exclude
        # the iterator contents from it
        children = node.iter_child_nodes(exclude=('iter',))
        if node.recursive:
            loop_frame = self.function_scoping(node, frame, children,
                                               find_special=False)
        else:
            loop_frame = frame.inner()
            loop_frame.inspect(children)

        # try to figure out if we have an extended loop.  An extended loop
        # is necessary if the loop is in recursive mode if the special loop
        # variable is accessed in the body.
        extended_loop = node.recursive or 'loop' in \
                        find_undeclared(node.iter_child_nodes(
                            only=('body',)), ('loop',))

        # if we don't have an recursive loop we have to find the shadowed
        # variables at that point.  Because loops can be nested but the loop
        # variable is a special one we have to enforce aliasing for it.
        if not node.recursive:
            aliases = self.push_scope(loop_frame, ('loop',))

        # otherwise we set up a buffer and add a function def
        else:
            assert False, "cannot into recursive loops"
            self.writeline('def loop(reciter, loop_render_func):', node)
            self.indent()
            self.buffer(loop_frame)
            aliases = {}

        # make sure the loop variable is a special one and raise a template
        # assertion error if a loop tries to write to loop
        if extended_loop:
            loop_frame.identifiers.add_special('loop')
        for name in node.find_all(nodes.Name):
            if name.ctx == 'store' and name.name == 'loop':
                self.fail('Can\'t assign to special loop variable '
                          'in for-loop target', name.lineno)

        self.pull_locals(loop_frame)
        if node.else_:
            iteration_indicator = self.temporary_identifier()
            self.writeline('%s = 1' % iteration_indicator)

        # Create a fake parent loop if the else or test section of a
        # loop is accessing the special loop variable and no parent loop
        # exists.
        if 'loop' not in aliases and 'loop' in find_undeclared(
           node.iter_child_nodes(only=('else_', 'test')), ('loop',)):
            self.writeline("l_loop = environment.undefined(%r, name='loop')" %
                ("'loop' is undefined. the filter section of a loop as well "
                 "as the else block don't have access to the special 'loop'"
                 " variable of the current loop.  Because there is no parent "
                 "loop it's undefined.  Happened in loop on %s" %
                 self.position(node)))

        if extended_loop:
            self.writeline("var l_loop={}");
            self.writeline("var __length = ")
            self.visit(node.iter, loop_frame)
            self.write(".length;")

        self.writeline('for(var __i=0;__i< ', node)
        self.write("__length; __i++)")

        # if we have an extened loop and a node test, we filter in the
        # "outer frame".
        if extended_loop and node.test is not None:
            self.write('(')
            self.visit(node.target, loop_frame)
            self.write(' for ')
            self.visit(node.target, loop_frame)
            self.write(' in ')
            if node.recursive:
                self.write('reciter')
            else:
                self.visit(node.iter, loop_frame)
            self.write(' if (')
            test_frame = loop_frame.copy()
            self.visit(node.test, test_frame)
            self.write('))')

        elif node.recursive:
            self.write('reciter')
        #else:
        #    self.visit(node.iter, loop_frame)

        if node.recursive:
            self.write(', recurse=loop_render_func):')

        # tests in not extended loops become a continue
        if not extended_loop and node.test is not None:
            assert False, "extented loop with test"
            self.indent()
            self.writeline('if not ')
            self.visit(node.test, loop_frame)
            self.write(':')
            self.indent()
            self.writeline('continue')
            self.outdent(2)

        self.indent()

        #XXX: this sucks
        if extended_loop:
            self.writeline("l_loop.index = __i+1")
            self.writeline("l_loop.index0 = __i")
            self.writeline("l_loop.first = (__i==0)")
            self.writeline("l_loop.last = (__i+1 == __length)")
            self.writeline("l_loop.revindex = __length - __i")
            self.writeline("l_loop.revindex = __length - __i - 1")



        self.writeline("var ", node.target);
        self.visit(node.target, loop_frame);
        self.write(" = ")
        self.visit(node.iter, loop_frame)
        self.write("[__i];")
        self.blockvisit(node.body, loop_frame)
        if node.else_:
            self.writeline('%s = 0' % iteration_indicator)
        self.outdent()

        if node.else_:
            self.writeline('if(%s)' % iteration_indicator)
            self.indent()
            self.blockvisit(node.else_, loop_frame)
            self.outdent()

        # reset the aliases if there are any.
        if not node.recursive:
            self.pop_scope(aliases, loop_frame)

        # if the node was recursive we have to return the buffer contents
        # and start the iteration code
        if node.recursive:
            self.return_buffer_contents(loop_frame)
            self.outdent()
            self.start_write(frame, node)
            self.write('loop(')
            self.visit(node.iter, frame)
            self.write(', loop)')
            self.end_write(frame)


    def visit_If(self, node, frame):
        if_frame = frame.soft()
        self.writeline('if( ', node)
        self.visit(node.test, if_frame)
        self.write(')')
        self.indent()
        self.blockvisit(node.body, if_frame)
        self.outdent()
        if node.else_:
            self.writeline('else')
            self.indent()
            self.blockvisit(node.else_, if_frame)
            self.outdent()

    def macro_body(self, node, frame, children=None):
        """Dump the function def of a macro or call block."""
        frame = self.function_scoping(node, frame, children)
        # macros are delayed, they never require output checks
        frame.require_output_check = False
        args = frame.arguments
        # XXX: this is an ugly fix for the loop nesting bug
        # (tests.test_old_bugs.test_loop_call_bug).  This works around
        # a identifier nesting problem we have in general.  It's just more
        # likely to happen in loops which is why we work around it.  The
        # real solution would be "nonlocal" all the identifiers that are
        # leaking into a new python frame and might be used both unassigned
        # and assigned.
        if 'loop' in frame.identifiers.declared:
            args = args + ['var l_loop=l_loop']
        self.writeline('var macro = function(%s)' % ', '.join(args), node)
        self.indent()
        self.buffer(frame)
        self.pull_locals(frame)
        self.blockvisit(node.body, frame)
        self.return_buffer_contents(frame)
        self.outdent()
        return frame


    def macro_def(self, node, frame):
        """Dump the macro definition for the def created by macro_body."""
        arg_tuple = ', '.join(repr(x.name) for x in node.args)
        name = getattr(node, 'name', None)
        if len(node.args) == 1:
            arg_tuple += ','
        self.write('Macro(environment, macro, %r, [%s], [' %
                   (name, arg_tuple))
        for arg in node.defaults:
            self.visit(arg, frame)
            self.write(', ')
        self.write('], %s, %s, %s)' % (
            jbool(frame.accesses_kwargs),
            jbool(frame.accesses_varargs),
            jbool(frame.accesses_caller)
        ))



ModuleLoader.get_module_filename = classmethod(fname)
compiler.CodeGenerator = JsGenerator


env = Environment(loader= FileSystemLoader("./tpls"))
env.compile_templates("./data/js/tpl/", zip=None,
        log_function = print)
