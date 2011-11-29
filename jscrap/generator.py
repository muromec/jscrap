from __future__ import print_function

from jinja2 import Environment, FileSystemLoader, ModuleLoader
from jinja2 import compiler
from jinja2.compiler import Frame, find_undeclared, CompilerExit

from jinja2 import nodes
from jinja2.nodes import EvalContext
from jinja2.utils import Markup, concat, escape, is_python_keyword, next

js_keywords = ['return', 'continue', 'function', 'default']

def fname(cls, s):
    return s.replace(".html", '')+".js"


class JsNone(object):
    def __repr__(self):
        return 'undefined'

    def __nonzero__(self):
        return False

JsNone = JsNone()

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

        self.safename = self.name.replace(".","_")
        self.writeline('var tpl_%s = new function()' % self.safename)
        self.indent()

        frame = Frame(eval_ctx)
        frame.inspect(node.body)
        frame.toplevel = frame.rootlevel = True
        frame.require_output_check =  not self.has_known_extends

        self.buffer(frame)
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
                self.writeline('l_super = context.super_block(block_%s)' % name)
            self.pull_locals(block_frame)
            self.pull_dependencies(block.body)
            self.blockvisit(block.body, block_frame)
            self.outdent()

        self.writeline('var blocks = {%s};' % ', '.join('%r: block_%s' % (x, x)
                                                   for x in self.blocks),
                       extra=1)

        self.writeline("var name = %r"% self.name)
        self.writeline('return')
        self.indent()
        self.writeline('name:  name,')

        self.writeline('root: function(context)', extra=1)


        self.indent()
        self.writeline('if(context.blocks==undefined)')
        self.indent()
        self.writeline("context.blocks=blocks")
        self.outdent()

        self.clear_buffer(frame)
        self.writeline('var parent_template = null;')

        if 'self' in find_undeclared(node.body, ('self',)):
            frame.identifiers.add_special('self')
            self.writeline('l_self = context.call_blocks()')

        self.pull_locals(frame)
        self.pull_dependencies(node.body)
        self.blockvisit(node.body, frame)

        self.writeline("if(parent_template)")
        self.indent()
        self.writeline('return parent_template.root(context)')
        self.outdent()

        self.return_buffer_contents(frame)
        self.outdent()

        """
        if not self.has_known_extends:
            self.indent()
            self.writeline('if parent_template is not None:')
        self.indent()
        """



        self.write(',')
        self.writeline('blocks: blocks')

        self.outdent()
        self.outdent()
        self.writeline('if(typeof(environment)!="undefined")')
        self.indent()
        self.writeline('environment.tpl[%r] = tpl_%s' % (self.name, self.safename))
        self.outdent()


    def visit_Block(self, node, frame):
        """Call a block and register it for the template."""
        if frame.toplevel:
            # if we know that we are a child template, there is no need to
            # check if we are one
            if self.has_known_extends:
                return

        self.writeline('context.blocks[%r](context' % node.name)

        if node.scoped:
            self.write('.clone(')
            self.indent()
            to_copy = frame.identifiers.declared_locally
            for varname in to_copy:
                self.writeline("%s: l_%s"%(varname,varname))

            self.outdent()
            self.writeline(')')


        self.write(', %s)' % frame.buffer)


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

    def clear_buffer(self, frame):
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
        if node.attr in js_keywords:
            attr = "__%s" % node.attr
        else:
            attr = node.attr
        self.write('[%r]' % attr)

    def pull_dependencies(self, nodes):
        """Pull all the dependencies."""
        visitor = compiler.DependencyFinderVisitor()
        for node in nodes:
            visitor.visit(node)
        for dependency in 'filters', 'tests':
            mapping = getattr(self, dependency)
            for name in getattr(visitor, dependency):
                if name not in mapping:
                    mapping[name] = self.temporary_identifier()

                if name in js_keywords:
                    js_name = "__%s" % name
                else:
                    js_name = name

                self.writeline('%s = environment.%s[%r]' %
                               (mapping[name], dependency, js_name))



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

        aliases = self.push_scope(loop_frame, ('loop',))

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


        self.writeline("var __iter_map=function(")#__current,__i)")
        if not isinstance(node.target, nodes.Tuple):
            self.visit(node.target, loop_frame)
        else:
            self.write("__current")

        self.write(",__i)")

        self.indent()

        #XXX: this sucks
        if extended_loop:
            self.writeline("var l_loop= new environment.Loop(__i,");
            self.visit(node.iter, loop_frame)
            self.write(".length, __iter_map);")


        def setvar(node_target, node_iter, idx=None):
            self.writeline("var ", node_target);
            self.visit(node_target, loop_frame);
            self.write(" = ")
            self.write("__current[%d];"%idx)

        if isinstance(node.target, nodes.Tuple):
            for idx,item in enumerate(node.target.items):
                setvar(item, node.iter, idx)

        if node.test is not None:
            self.writeline('if(! ')
            self.visit(node.test, loop_frame)
            self.write(') return')

        self.blockvisit(node.body, loop_frame)
        if node.else_:
            self.writeline('%s = 0' % iteration_indicator)
        self.outdent()

        self.writeline("if((")
        self.visit(node.iter, loop_frame)
        self.write("!==undefined)&&")
        self.visit(node.iter, loop_frame)
        self.write(".map)")

        self.visit(node.iter, loop_frame)
        self.write(".map(__iter_map)")

        self.writeline("else if((")
        self.visit(node.iter, loop_frame)
        self.write("!==undefined)&&")
        self.visit(node.iter, loop_frame)
        self.write(".length)")
        self.indent()
        self.writeline("for(var __i=0;__i<")
        self.visit(node.iter, loop_frame)
        self.write(".length;__i++)")
        self.indent()
        self.writeline("__iter_map(")
        self.visit(node.iter, loop_frame)
        self.write("[__i], __i)")
        self.outdent()
        self.outdent()

        if node.else_:
            self.writeline('if(%s)' % iteration_indicator)
            self.indent()
            self.blockvisit(node.else_, loop_frame)
            self.outdent()

        self.pop_scope(aliases, loop_frame)


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
        self.clear_buffer(frame)

        self.pull_locals(frame)
        self.blockvisit(node.body, frame)
        self.return_buffer_contents(frame)
        self.outdent()
        return frame


    def macro_def(self, node, frame):
        """Dump the macro definition for the def created by macro_body."""
        arg_tuple = ', '.join(repr(x.name) for x in node.args)
        name = getattr(node, 'name', JsNone)
        if len(node.args) == 1:
            arg_tuple += ','
        self.write('new Macro(environment, macro, %r, [%s], [' %
                   (name, arg_tuple))
        for arg in node.defaults:
            self.visit(arg, frame)
            self.write(', ')
        self.write('], %s, %s, %s)' % (
            jbool(frame.accesses_kwargs),
            jbool(frame.accesses_varargs),
            jbool(frame.accesses_caller)
        ))

    def visit_CallBlock(self, node, frame):
        children = node.iter_child_nodes(exclude=('call',))
        call_frame = self.macro_body(node, frame, children)
        self.writeline('var caller = ')
        self.macro_def(node, call_frame)
        self.start_write(frame, node)
        self.visit_Call(node.call, call_frame, forward_caller=True)
        self.end_write(frame)

    def visit_Call(self, node, frame, forward_caller=False):
        if self.environment.sandboxed:
            self.write('environment.call(context, ')
        else:
            self.write('context.call(')
        self.visit(node.node, frame)
        extra_kwargs = forward_caller and {'caller': 'caller'} or None
        self.signature(node, frame, extra_kwargs)
        self.write(')')


    def start_write(self, frame, node=None):
        """Yield or write into the frame buffer."""
        self.writeline('%s.push(' % frame.buffer, node)


    def visit_FromImport(self, node, frame):
        """Visit named imports."""
        self.newline(node)
        self.write('var included_template = environment.get_template(')
        self.visit(node.template, frame)
        self.write(', %r)' % self.name)
        self.writeline('included_template.context = context.clone()')
        self.writeline('included_template.root(included_template.context)')

        var_names = []
        discarded_names = []
        for name in node.names:
            if isinstance(name, tuple):
                name, alias = name
            else:
                alias = name
            self.writeline('l_%s = included_template.context.exported_vars.resolve(%r)' % (alias, name))
            self.writeline('if (l_%s === undefined)' % alias)
            self.indent()
            self.writeline('throw ReferenceError("Included template doesn not '
                    'export %r")' % name)
            self.outdent()
            if frame.toplevel:
                var_names.append(alias)
                if not alias.startswith('_'):
                    discarded_names.append(alias)
            frame.assigned_names.add(alias)

        if var_names:
            if len(var_names) == 1:
                name = var_names[0]
                self.writeline('context.vars[%r] = l_%s' % (name, name))
            else:
                self.writeline('context.vars.update({%s})' % ', '.join(
                    '%r: l_%s' % (name, name) for name in var_names
                ))
        if discarded_names:
            if len(discarded_names) == 1:
                self.writeline('context.exported_vars.discard(%r)' %
                               discarded_names[0])
            else:
                self.writeline('context.exported_vars.difference_'
                               'update((%s))' % ', '.join(map(repr, discarded_names)))

    def uaop(operator, interceptable=True):
        def visitor(self, node, frame):
            if self.environment.sandboxed and \
               operator in self.environment.intercepted_unops:
                self.write('environment.call_unop(context, %r, ' % operator)
                self.visit(node.node, frame)
            else:
                self.write('(' + operator)
                self.visit(node.node, frame)
            self.write(')')
        return visitor


    visit_Not = uaop('! ', interceptable=False)

    def signature(self, node, frame, extra_kwargs=None):
        for arg in node.args:
            self.write(', ')
            self.visit(arg, frame)

        for kwarg in node.kwargs:
            self.write(', ')
            self.visit(kwarg, frame)

        if node.dyn_args:
            self.write(', {__vararg:')
            self.visit(node.dyn_args, frame)
            self.write("}")

        if extra_kwargs is not None:
            self.write(", {")
            for key, value in extra_kwargs.iteritems():
                self.write('%s:%s,' % (key, value))

            self.write("}")

    def visit_Const(self, node, frame):
        val = node.value
        if isinstance(val, float):
            self.write(str(val))
        elif isinstance(val, bool):
            self.write(jbool(val))
        elif val is None:
            self.write("undefined")
        else:
            self.write(repr(val))


    def visit_Extends(self, node, frame):
        """Calls the extender."""
        if not frame.toplevel:
            self.fail('cannot use extend from a non top-level scope',
                      node.lineno)

        self.writeline('parent_template = environment.get_template(', node)
        self.visit(node.template, frame)
        self.write(', %r)' % self.name)
        self.writeline("var _blocks = parent_template.blocks;")
        self.writeline("var _blocks_keys = Object.keys(_blocks);")



        self.writeline('for(var i=0;i<_blocks_keys.length;i++)')
        self.indent()
        self.writeline("var name = _blocks_keys[i]");
        self.writeline("if(context.blocks[name])")
        self.indent()
        self.writeline("context.blocks[name]._super = _blocks[name]")
        self.writeline("continue")
        self.outdent()
        self.writeline('context.blocks[name] = _blocks[name]')
        self.outdent()

        # if this extends statement was in the root level we can take
        # advantage of that information and simplify the generated code
        # in the top level from this point onwards
        if frame.rootlevel:
            self.has_known_extends = True

        # and now we have one more
        self.extends_so_far += 1



if __name__ == '__main__':

    import sys
    inp,out = sys.argv[1:3]
    from jinja2.parser import Parser

    env = Environment(loader= FileSystemLoader(inp))

    def jinja_compile(source, name, generator):
        code = Parser(env, source)
        gen = generator(env, name, name)
        gen.visit(code.parse())
        return gen.stream.getvalue()


    for tpl in env.loader.list_templates():
        _source,_,_ = env.loader.get_source(env, tpl)

        jsname = tpl.replace(".", "__")
        js_file = open("%s/%s.js" % (out, jsname), 'w')
        js_file.write( jinja_compile(_source, jsname, JsGenerator))
        js_file.close()

        """
        py_file = open("%s/%s.py" % (out, tpl), 'w')
        py_file.write( jinja_compile(_source, tpl, compiler.CodeGenerator))
        py_file.close()
        """
