// Forecast preview for the home page: runs the Forecast Method Comparison engine on three of its sample files
// (24-month test window, 6 months ahead, the tool's defaults) and writes fc.json. Run: node prep_fc.js
const fs=require("fs"),path=__dirname+"/../forecast-compare/",E=require(path+"engine.js");
const S=[["SAMPLE_demand","Sample demand (made-up)","units"],["DJFUELUSGULF","Jet fuel, US Gulf Coast (EIA)","$/gal"],["PCU322211322211","Corrugated boxes price index (BLS)","index"]];
const names=Object.fromEntries(E.METHODS.map(m=>[m.id,m.name]));
const out=[];
for(const [f,label,unit] of S){
  const rows=fs.readFileSync(path+"data/"+f+".csv","utf8").trim().split(/\r?\n/).slice(1).map(l=>l.split(","));
  const y=rows.map(r=>+r[1]), d=rows.map(r=>r[0].slice(0,7));
  const P=E.prepare(y,12,null,[],2*36+12+E.CAL-1), r=E.score(P,{h:6,test:24}), ranked=E.rank(r.results,r.rankBy);
  const g=E.ranges(P,{h:6,test:24,kind:"pool",levels:[0.5,0.8,0.95]});
  const rd=v=>+v.toPrecision(5);
  out.push({id:f,label,unit,rankBy:r.rankBy,months:d.slice(-48),y:y.slice(-48).map(rd),
    methods:ranked.map(x=>({id:x.id,name:names[x.id]||x.id,err:+x.metrics[r.rankBy].toFixed(3),in:r.members.includes(x.id)})),
    fc:r.pool.future.slice(0,6).map((v,k)=>({mid:rd(v),lo:rd(v+g.future[k].lo[1]),hi:rd(v+g.future[k].hi[1])}))});
}
fs.writeFileSync(__dirname+"/fc.json",JSON.stringify(out));
for(const o of out) console.log(o.label,o.months.at(-1),o.rankBy,o.methods.slice(0,4).map(m=>m.name+" "+m.err).join(" | "),"n="+o.methods.length,JSON.stringify(o.fc[5]));
