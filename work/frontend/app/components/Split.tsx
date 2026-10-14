"use client";

import { ReactNode, useRef, useState } from "react";

interface Props {
  id: string;
  direction: "horizontal" | "vertical";
  percent: number;
  containerClass: string;
  firstClass: string;
  secondClass: string;
  first: ReactNode;
  second: ReactNode;
}

const MIN_EDGE_PX = 4;
const SPLITTER_PX = 5;

/** Two panels with a draggable bar between them (port of the original jQuery `split` plugin). */
export default function Split({ id, direction, percent, containerClass, firstClass, secondClass, first, second }: Props) {
  const vertical = direction === "vertical";
  const [size, setSize] = useState(percent);
  const container = useRef<HTMLDivElement>(null);

  function startDrag() {
    const move = (event: MouseEvent) => {
      const box = container.current?.getBoundingClientRect();
      if (!box) return;
      const total = vertical ? box.height : box.width;
      const at = vertical ? event.clientY - box.top : event.clientX - box.left;
      if (at > MIN_EDGE_PX && at < total - MIN_EDGE_PX) setSize((at / total) * 100);
    };
    const stop = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", stop);
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", stop);
  }

  const dimension = vertical ? "height" : "width";
  return (
    <div id={id} ref={container} className={containerClass}>
      <div className={firstClass} style={{ [dimension]: `${size}%` }}>
        {first}
      </div>
      <div
        className="splitter"
        data-testid={`${id}-bar`}
        style={{ [dimension]: SPLITTER_PX, cursor: vertical ? "row-resize" : "col-resize" }}
        onMouseDown={startDrag}
      />
      <div className={secondClass} style={{ [dimension]: `${100 - size}%` }}>
        {second}
      </div>
    </div>
  );
}
