import { useEffect, useLayoutEffect, useRef, useState } from 'react';

export interface Size {
  width: number;
  height: number;
}

/**
 * Observes an element with ResizeObserver (rAF-throttled) so canvas geometry
 * follows the CSS box instead of guessing from window.innerHeight.
 */
export function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });
  const frame = useRef<number>(0);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;

    const measure = () => {
      const rect = el.getBoundingClientRect();
      setSize((prev) => {
        const width = Math.max(0, Math.round(rect.width));
        const height = Math.max(0, Math.round(rect.height));
        return prev.width === width && prev.height === height
          ? prev
          : { width, height };
      });
    };

    measure();

    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(measure);
    });
    observer.observe(el);

    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame.current);
    };
  }, []);

  return { ref, size };
}

/** Tracks devicePixelRatio + viewport, including live DPR changes (zoom / screen move). */
export function useDisplayProfile() {
  const read = () => ({
    dpr: window.devicePixelRatio || 1,
    width: window.innerWidth,
    height: window.innerHeight,
  });
  const [profile, setProfile] = useState(read);

  useEffect(() => {
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const next = read();
        setProfile((prev) =>
          prev.dpr === next.dpr && prev.width === next.width && prev.height === next.height
            ? prev
            : next,
        );
      });
    };

    window.addEventListener('resize', update);

    let mq: MediaQueryList | null = null;
    const watchDpr = () => {
      mq?.removeEventListener('change', onDpr);
      mq = window.matchMedia('(resolution: ' + (window.devicePixelRatio || 1) + 'dppx)');
      try {
        mq.addEventListener('change', onDpr);
      } catch {
        mq.addListener(onDpr);
      }
    };
    const onDpr = () => {
      update();
      watchDpr();
    };

    watchDpr();

    return () => {
      window.removeEventListener('resize', update);
      cancelAnimationFrame(frame);
      try {
        mq?.removeEventListener('change', onDpr);
      } catch {
        mq?.removeListener(onDpr);
      }
    };
  }, []);

  return profile;
}

/** Locks body scrolling and binds Escape while a dialog/drawer is open. */
export function useModalBehavior(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onClose();
      }
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);
}
