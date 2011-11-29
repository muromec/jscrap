var page = new WebPage();
var ret, render=false, entry='main'

page.onConsoleMessage = function (msg) {
    console.log("page: "+msg);
};

page.injectJs("../bootstrap.js");
page.viewportSize = { width: 480, height: 800 }

for(var i=0; i<phantom.args.length;i++) {
    if(phantom.args[i] == 'render') {
        render=true;
        continue;
    }
    ret = page.injectJs(phantom.args[i]);
}


console.log(page.evaluate(function() {
    var ctx = new Context(param);
    try {
        ret = environment.tpl[param._entry].root(ctx);
    } catch(e) {
        console.log(e)
        console.log(e.arguments)
        return
    }
    try {
        document.write(ret)
    } catch(e) {
        true;
    }
    return ret;
}))
if (render)
    page.render("screen.png");
phantom.exit();
