// XXX: move out, drop global
environment = new (function(){
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
    }
})();


// XXX:damn global
Macro = function(env, func, fname, _args, _defs, 
accesses_kwargs, accesses_varargs, accesses_caller) {

    return func;

}

var Context = function(param) {
    
    var exported_vars = [];
    var _vars = {};

    return {
        
        resolve: function(vname){
            return param[vname];
        },
        exported_vars: {
            add: function(vname) {
                exported_vars.push(vname)
            }
        },
        vars: _vars,
        call: function(f, _arg0) {
            return f(_arg0)
        }
    }
}
