var page = new WebPage();
var ret, render=false;

page.injectJs("../bootstrap.js");
page.viewportSize = { width: 480, height: 800 }

for(var i=0; i<phantom.args.length;i++) {
    if(phantom.args[i] == 'render') {
        render=true;
        continue;
    }
    ret = page.injectJs(phantom.args[i]);
}

page.onConsoleMessage = function (msg) { 
    console.log("page: "+msg); 
};


console.log(page.evaluate(function() {
    var ctx = new Context(param);
    ret = tpl_main.root(ctx);
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
