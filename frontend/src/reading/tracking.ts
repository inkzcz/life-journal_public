export function readingProgress(scroll: number, start: number, height: number, viewport: number) {
  if(height<=viewport)return scroll+viewport>=start+height?100:0
  return Math.round(Math.min(1,Math.max(0,(scroll-start)/Math.max(1,height-viewport)))*100)
}
export function currentHeading(offsets: number[], scroll: number, viewport: number) {
  const line=scroll+Math.min(120,viewport*.2)
  let current=0
  // Offsets are monotonic. Binary search avoids scanning a long TOC each frame.
  let low=0,high=offsets.length-1
  while(low<=high){const middle=(low+high)>>>1;if(offsets[middle]!<=line){current=middle;low=middle+1}else high=middle-1}
  return current
}

// Hidden descendants of a closed details element have zero geometry. Track
// the visible outer summary instead so chapter offsets remain monotonic.
export function visibleReadingTarget(node:HTMLElement,boundary:HTMLElement){
 let target=node,parent=node.parentElement
 while(parent&&parent!==boundary){if(parent instanceof HTMLDetailsElement&&!parent.open)target=parent;parent=parent.parentElement}
 return target
}
