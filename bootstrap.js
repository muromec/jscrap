// XXX: move out, drop global
environment = new (function(){
    var tpl_reg = {}
    var array_stringify = function() {
        return "["+this.join(", ")+"]"
    }
    Array.prototype.toString = array_stringify;

    return {
        getitem: function(iterable, idx) {
            if (!iterable)
                return

            if(idx<0) idx = iterable.length + idx;

            return iterable[idx];
        },
        filters: {
            join: function(ctx, iterable, chr) {
                return iterable.join(chr);
            },
            batch: function(iterable, bsize, fll) {
                var ret = [],
                   current = [];

                if(typeof(fll) == 'string')
                    fll = "'"+fll.replace("'", "\\'")+"'" // XXX: proper escape

                for(var i=0;i<iterable.length;i++) {
                    current.push(iterable[i])

                    if(current.length >= bsize) {
                        ret.push(current);
                        current = []
                    }
                }
                if(current.length && fll!==undefined) {
                    while(current.length < bsize)
                        current.push(fll)
                }
                if(current.length)
                    ret.push(current)

                return ret;
            },
            list: function(iterable) {
                return Array.prototype.slice.call(iterable)

            },
            lower: function(str) {
                return str.toString().toLowerCase()
            },
            upper: function(str) {
                return str.toString().toUpperCase()
            },
            escape: function(str) {
                // XXX: need proper escape
                return str.toString().replace("<","&lt;").replace(">","&gt;")
            },
            /*
            center: function(str) {
                console.log("center")
                return str.center()
            },*/
            first: function(env, iter) {
                return iter[0]
            },
            __default: function(str, d) {
                return (str || d)
            },
            dictsort: function(obj, case_s, by) {
                var ret = [];
                var idx = 0;
                if(by == 'value')
                    idx = 1;

                var sort_func = function(a, b) {
                    a = a[idx]
                    b = b[idx]

                    if(!case_s) {
                        a = a.toString().toLowerCase()
                        b = b.toString().toLowerCase()
                    }
                    if(a>b) return 1
                    if(b>a) return -1

                    return 0
                }

                var key = Object.keys(obj)
                for(var i=0; i<key.length; i++)
                    ret.push([key[i], obj[key[i]]])

                return ret.sort(sort_func)
            },
        },
        get_template: function(tpl, frm) {
            return tpl_reg[tpl]
        },
        tpl: tpl_reg,
        tests: {
            defined: function(arg) {
                return arg != undefined;
            },
            even: function(arg) {
                return (arg %2)==0;
            },
        },
        Loop: function(iter, length,__iter_map) {
            return {
                index: iter+1,
                index0: iter,
                first: (iter==0),
                last: (iter+1 == length),
                revindex: length - iter,
                revindex0: length - iter - 1,
                length: length,
                cycle: {
                    func:function() {
                        return arguments[iter % arguments.length];
                    }
                },
                func: function(item) {
                    // XXX: handle undefined and so on
                    // XXX: duplicates generated code

                    /*
                     * placing here "return" statement
                     * adds one "," to output
                     */
                    item.map(__iter_map)
                },
            }
        },
    }
})();


// XXX:damn global
Macro = function(env, func, fname, _args, _defs, 
accesses_kwargs, accesses_varargs, accesses_caller) {
    var args = {
    }
    var skip = _args.length - _defs.length;
    var def_n = 0;
    for(var i=0; i<_args.length; i++) {
        if(skip > 0) {
            skip--;
            continue;
        }

        args[i] = _defs[def_n]
        def_n++;
    }

    return {
        func: func,
        accesses_kwargs: accesses_kwargs,
        accesses_varargs: accesses_varargs,
        accesses_caller: accesses_caller,
        args: args,
        max_args: _args.length,
        name: fname,
        argnames: _args,
    }

}

var Context = function(param) {
    
    var exported_vars = {};
    var _vars = {
        range: {
            func: function(_f,_t) {
                var ret = [];
                if(_t===undefined) {
                    _t = _f;
                    _f = 0;
                }
                for(;_f<_t;_f++)
                    ret.push(_f)

                return ret;
            }
        }
    }
    var _param = param || {};

    return {

        clone: function(_add) {
            var param_copy = {};

            for(var key in _param)
                param_copy[key] = _param[key];

            for(var key in _add)
                param_copy[key] = _add[key];

            var ctx = new Context(param_copy);

            for(var key in exported_vars)
                ctx.exported_vars.add(key)

            for(var key in _vars)
                ctx.vars[key] = _vars[key]

            return ctx;

        },
        
        resolve: function(vname){

            if(_param[vname]!==undefined)
                return _param[vname];

            return _vars[vname];
        },
        exported_vars: {
            add: function(vname) {
                exported_vars[vname] = true;
            },
            discard: function() {}, // wtf
            resolve: function(vname) {
                if(exported_vars[vname])
                    return _vars[vname];
            },

        },
        vars: _vars,
        call_blocks: function() {
            var ret = {},
                ctx = this;
            for(bkey in this.blocks) {
                ret[bkey] = {
                    func: (function(b){
                        return function() {
                            var buf = [];
                            b(ctx, buf);
                            return buf.join("")
                        }
                    })(this.blocks[bkey])
                }
            }
            return ret;
        },
        super_block: function(block) {
            var ctx = this;
            return {
                func: function(){
                    var buf = []
                    block._super(ctx, buf)
                    return buf.join("")
                }
            }
        },
        call: function(f, _arg0) {

            var args = [],
                varargs = Array.prototype.slice.call(arguments);

            varargs.shift()

            for(var i=0;i<f.max_args;i++) {
                args[i] = varargs[i]

                if(!varargs[i])
                    args[i] = f.args[i]
            }
            if(f.max_args==undefined)
                args = varargs;

            if(args.length && args[args.length-1].__vararg) {

                args = args.concat(args.pop().__vararg);
            }

            /*
            if(f.accesses_kwargs) {
                var kw = varargs[varargs.length-1];
                console.log("kw :"+kw.keys())

                for(var i=0;i<f.argnames.length;i++)
                    args[i] = kw[f.argnames[i]];
            }*/

            if(f.accesses_varargs) {
                args.push(varargs)
            }

            if(f.accesses_caller) {
                var kwargs = varargs.pop()
                if(kwargs && kwargs.caller)
                    args.push(kwargs.caller)
            }

            return f.func.apply(null, args)
        }
    }
}
concat = function(iter) { return iter.join("")}
