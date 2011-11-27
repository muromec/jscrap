// XXX: move out, drop global
environment = new (function(){
    var tpl_reg = {}
    return {
        getitem: function(iterable, idx) {
            if (!iterable)
                return

            return iterable[idx];
        },
        filters: {
            join: function(ctx, iterable, chr) {
                return iterable.join(chr);
            }
        },
        get_template: function(tpl, frm) {
            return tpl_reg[tpl]
        },
        tpl: tpl_reg,
        tests: {
            defined: function(arg) {
                return arg != undefined;
            }
        },
        Loop: function(iter, length) {
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
    var _vars = {};
    var _param = param || {};

    return {
        
        resolve: function(vname){

            return _param[vname] || _vars[vname];
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
