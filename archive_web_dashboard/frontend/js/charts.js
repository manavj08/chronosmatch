const ctx=document.getElementById('chart');

new Chart(ctx,{

type:'line',

data:{

labels:['9 AM','10 AM','11 AM','12 PM','1 PM','2 PM','3 PM'],

datasets:[{

label:'Orders',

data:[100,120,150,180,220,250,280],

borderColor:'#38bdf8',

backgroundColor:'rgba(56,189,248,.2)',

fill:true,

tension:.4

}]

},

options:{

responsive:true

}

});