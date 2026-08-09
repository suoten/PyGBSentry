/** External library type declarations */

// SortableJS
declare module 'sortablejs' {
  class Sortable {
    constructor(el: HTMLElement, options?: Sortable.Options)
    destroy(): void
    static create(el: HTMLElement, options?: Sortable.Options): Sortable
  }

  namespace Sortable {
    interface Options {
      group?: string | { name: string; pull?: boolean | Function; put?: boolean | Function }
      sort?: boolean
      delay?: number
      touchStartThreshold?: number
      disabled?: boolean
      animation?: number
      easing?: string | Function
      draggable?: string
      filter?: string | Function
      preventOnFilter?: boolean
      ghostClass?: string
      chosenClass?: string
      dragClass?: string
      forceFallback?: boolean
      fallbackClass?: string
      fallbackOnBody?: boolean
      fallbackTolerance?: number
      scroll?: boolean | HTMLElement
      scrollSensitivity?: number
      scrollSpeed?: number
      bubbleScroll?: boolean
      dragoverBubble?: boolean
      dataIdAttr?: string
      delayOnTouchOnly?: boolean
      swapThreshold?: number
      invertSwap?: boolean
      removedMode?: string
      direction?: string
      onChoose?: (evt: SortableEvent) => void
      onUnchoose?: (evt: SortableEvent) => void
      onStart?: (evt: SortableEvent) => void
      onEnd?: (evt: SortableEvent) => void
      onAdd?: (evt: SortableEvent) => void
      onUpdate?: (evt: SortableEvent) => void
      onSort?: (evt: SortableEvent) => void
      onRemove?: (evt: SortableEvent) => void
      onFilter?: (evt: SortableEvent) => void
      onMove?: (evt: MoveEvent, originalEvent: Event) => boolean | void
      onClone?: (evt: SortableEvent) => void
      onChange?: (evt: SortableEvent) => void
    }

    interface SortableEvent {
      item: HTMLElement
      from: HTMLElement
      to: HTMLElement
      oldIndex: number
      newIndex: number
      oldDraggableIndex: number
      newDraggableIndex: number
      clone: HTMLElement
      pulled: HTMLElement
      put: HTMLElement
    }

    interface MoveEvent {
      dragged: HTMLElement
      draggedRect: DOMRect
      related: HTMLElement
      relatedRect: DOMRect
      willInsertAfter: boolean
    }
  }

  export = Sortable
}
