(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.SpectrumViewModel=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function lowerBound(values,target){let low=0,high=values.length;while(low<high){const mid=(low+high)>>1;if(values[mid]<target)low=mid+1;else high=mid;}return low;}
  function minMaxEnvelope(frame,minHz,maxHz,pixelCount){
    if(!frame||!frame.frequenciesHz||!frame.powersDbm||pixelCount<1)return[];
    const frequencies=frame.frequenciesHz,powers=frame.powersDbm;
    const start=lowerBound(frequencies,minHz),end=Math.min(frequencies.length,lowerBound(frequencies,maxHz+Number.EPSILON));
    if(start>=end)return[];
    const buckets=Math.max(1,Math.min(Math.floor(pixelCount),end-start)),points=[];
    for(let bucket=0;bucket<buckets;bucket+=1){
      const from=start+Math.floor((end-start)*bucket/buckets),to=start+Math.floor((end-start)*(bucket+1)/buckets);
      let minIndex=-1,maxIndex=-1,min=Infinity,max=-Infinity;
      for(let index=from;index<Math.max(from+1,to)&&index<end;index+=1){const value=powers[index];if(!Number.isFinite(value))continue;if(value<min){min=value;minIndex=index;}if(value>max){max=value;maxIndex=index;}}
      if(minIndex<0)continue;
      const ordered=minIndex===maxIndex?[minIndex]:(minIndex<maxIndex?[minIndex,maxIndex]:[maxIndex,minIndex]);
      for(const index of ordered)points.push({frequencyHz:frequencies[index],powerDbm:powers[index],index});
    }
    return points;
  }
  function peakInRange(frame,minHz,maxHz){
    if(!frame)return null;const start=lowerBound(frame.frequenciesHz,minHz),end=Math.min(frame.numPoints,lowerBound(frame.frequenciesHz,maxHz+Number.EPSILON));let best=null;
    for(let index=start;index<end;index+=1){const power=frame.powersDbm[index];if(Number.isFinite(power)&&(!best||power>best.powerDbm))best={frequencyHz:frame.frequenciesHz[index],powerDbm:power,index};}return best;
  }
  function sampleNearest(frame,frequencyHz){if(!frame||!frame.numPoints||!Number.isFinite(frequencyHz))return NaN;const first=frame.frequenciesHz[0],last=frame.frequenciesHz[frame.numPoints-1];if(frequencyHz<first||frequencyHz>last)return NaN;const index=lowerBound(frame.frequenciesHz,frequencyHz);const left=Math.max(0,index-1),right=Math.min(frame.numPoints-1,index);const selected=Math.abs(frame.frequenciesHz[left]-frequencyHz)<=Math.abs(frame.frequenciesHz[right]-frequencyHz)?left:right;return frame.powersDbm[selected];}
  class OverviewAccumulator{
    constructor({minFrequencyHz,maxFrequencyHz,bucketCount=24576,staleAfterMs=30000}){if(!(minFrequencyHz<maxFrequencyHz)||bucketCount<2)throw new TypeError('invalid overview configuration');this.minFrequencyHz=minFrequencyHz;this.maxFrequencyHz=maxFrequencyHz;this.bucketCount=bucketCount;this.staleAfterMs=staleAfterMs;this.values=new Float32Array(bucketCount);this.values.fill(NaN);this.updatedAt=new Float64Array(bucketCount);}
    bucketFor(frequencyHz){return Math.max(0,Math.min(this.bucketCount-1,Math.floor((frequencyHz-this.minFrequencyHz)/(this.maxFrequencyHz-this.minFrequencyHz)*this.bucketCount)));}
    frequencyFor(bucket){return this.minFrequencyHz+(bucket+.5)/this.bucketCount*(this.maxFrequencyHz-this.minFrequencyHz);}
    update(frame,nowMs=Date.now()){for(let index=0;index<frame.numPoints;index+=1){const frequency=frame.frequenciesHz[index],power=frame.powersDbm[index];if(frequency<this.minFrequencyHz||frequency>this.maxFrequencyHz||!Number.isFinite(power))continue;const bucket=this.bucketFor(frequency);this.values[bucket]=power;this.updatedAt[bucket]=nowMs;}}
    at(bucket,nowMs=Date.now()){const value=this.values[bucket],age=this.updatedAt[bucket]?Math.max(0,nowMs-this.updatedAt[bucket]):Infinity;return{value,valid:Number.isFinite(value),ageMs:age,stale:age>this.staleAfterMs};}
  }
  return{minMaxEnvelope,peakInRange,sampleNearest,OverviewAccumulator};
});
