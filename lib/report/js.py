REPORT_JS = r"""
(function(){
"use strict";

function reportData(){const e=document.getElementById("report-data");if(!e)return null;try{return JSON.parse(e.textContent)}catch(_){return null}}
function esc(v){return String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;")}
function formatKey(v){return String(v).replaceAll("_"," ").replace(/([a-z])([A-Z])/g,"$1 $2").replace(/\b\w/g,c=>c.toUpperCase())}
function formatValue(v){if(v===null||v===undefined)return "—";if(typeof v==="boolean")return v?"Yes":"No";return String(v)}
function duration(ms){if(ms===null||ms===undefined)return "—";if(ms<1000)return `${ms} ms`;const s=ms/1000;if(s<60)return `${s.toFixed(1)} s`;return `${Math.floor(s/60)}m ${Math.round(s%60)}s`}
function toggleStep(header){header.closest(".step")?.classList.toggle("open")}

function renderValue(value){
    if(value===null||value===undefined){
        return '<div class="result-empty">No data</div>';
    }

    if(typeof value!=="object"){
        return `
            <div class="result-value">
                <span class="result-value-text">${esc(formatValue(value))}</span>
            </div>
        `;
    }

    if(Array.isArray(value)){
        if(!value.length){
            return '<div class="result-empty">No data</div>';
        }

        return `
            <div class="result-list">
                ${value.map((item,index)=>`
                    <div class="result-list-item">
                        <span class="result-list-index">${index + 1}</span>
                        <div class="result-list-content">
                            ${typeof item==="object"
                                ? renderValue(item)
                                : `<span class="result-value-text">${esc(formatValue(item))}</span>`
                            }
                        </div>
                    </div>
                `).join("")}
            </div>
        `;
    }

    const entries=Object.entries(value);

    if(!entries.length){
        return '<div class="result-empty">No data</div>';
    }

    return `
        <div class="result-object">
            ${entries.map(([key,val])=>{
                const label=esc(formatKey(key));

                if(val===null||val===undefined){
                    return `
                        <div class="result-field">
                            <div class="result-field-label">${label}</div>
                            <div class="result-field-value muted">—</div>
                        </div>
                    `;
                }

                if(typeof val==="boolean"){
                    return `
                        <div class="result-field">
                            <div class="result-field-label">${label}</div>
                            <div class="result-field-value">
                                <span class="result-bool ${val?"true":"false"}">
                                    ${val?"Yes":"No"}
                                </span>
                            </div>
                        </div>
                    `;
                }

                if(typeof val==="object"){
                    return `
                        <div class="result-field result-field-object">
                            <div class="result-field-label">${label}</div>
                            <div class="result-field-value">
                                ${renderValue(val)}
                            </div>
                        </div>
                    `;
                }

                return `
                    <div class="result-field">
                        <div class="result-field-label">${label}</div>
                        <div class="result-field-value">
                            ${esc(formatValue(val))}
                        </div>
                    </div>
                `;
            }).join("")}
        </div>
    `;
}

function openResult(index){
    const report=reportData(), step=report?.steps?.[index];
    if(!step?.result)return;
    document.getElementById("result-title").textContent=`${step.name} — Plugin Result`;
    document.getElementById("result-pretty").innerHTML=renderValue(step.result);
    document.getElementById("result-raw-content").textContent=JSON.stringify(step.result,null,2);
    document.getElementById("result-pretty").style.display="block";
    document.getElementById("result-raw").style.display="none";
    document.querySelectorAll(".result-tab").forEach(b=>b.classList.toggle("active",b.dataset.view==="pretty"));
    document.getElementById("result-modal").classList.add("open");
}
function closeResult(){document.getElementById("result-modal")?.classList.remove("open")}
function setResultView(view){
    document.getElementById("result-pretty").style.display=view==="pretty"?"block":"none";
    document.getElementById("result-raw").style.display=view==="raw"?"block":"none";
    document.querySelectorAll(".result-tab").forEach(b=>b.classList.toggle("active",b.dataset.view===view));
}
function matches(step,filter){
    if(filter==="all")return true;
    if(filter==="success")return step.dataset.status==="COMPLETED";
    if(filter==="failed")return step.dataset.status==="FAILED";
    if(filter==="changed")return step.dataset.changed==="true";
    if(filter==="warnings")return step.dataset.warnings==="true";
    if(filter==="errors")return step.dataset.errors==="true";
    return true;
}
function applyFilters(){
    const filter=document.querySelector(".filter.active")?.dataset.filter||"all";
    const q=document.getElementById("report-search")?.value.toLowerCase().trim()||"";
    document.querySelectorAll(".step").forEach(step=>{
        const text=step.dataset.search||"";
        step.style.display=matches(step,filter)&&(!q||text.includes(q))?"":"none";
    });
}
function init(){
    document.querySelectorAll(".filter").forEach(b=>b.addEventListener("click",()=>{
        document.querySelectorAll(".filter").forEach(x=>x.classList.remove("active"));
        b.classList.add("active");applyFilters();
    }));
    document.getElementById("report-search")?.addEventListener("input",applyFilters);
    document.querySelectorAll("[data-result-index]").forEach(b=>b.addEventListener("click",e=>{e.stopPropagation();openResult(Number(b.dataset.resultIndex))}));
    document.getElementById("result-close")?.addEventListener("click",closeResult);
    document.getElementById("result-modal")?.addEventListener("click",e=>{if(e.target.id==="result-modal")closeResult()});
    document.querySelectorAll(".result-tab").forEach(b=>b.addEventListener("click",()=>setResultView(b.dataset.view)));
    document.addEventListener("keydown",e=>{if(e.key==="Escape")closeResult()});
}
window.toggleStep=toggleStep;
window.openResult=openResult;
document.addEventListener("DOMContentLoaded",init);
})();
"""
