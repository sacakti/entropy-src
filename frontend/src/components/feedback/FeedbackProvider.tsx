
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  AlertCircle,
  CheckCircle2,
  Info,
  LoaderCircle,
  TriangleAlert,
  X,
  XCircle,
} from 'lucide-react'
import './Feedback.css'

export type NotificationType =
  | 'success'
  | 'info'
  | 'warning'
  | 'error'

export interface NotificationOptions {
  title?: string
  message: string
  duration?: number
}

export interface ModalOptions {
  title: string
  message?: string
  confirmText?: string
  cancelText?: string
  destructive?: boolean
  dismissible?: boolean
  content?: ReactNode
}

interface NotificationItem extends NotificationOptions {
  id: number
  type: NotificationType
}

type ModalKind = 'confirm' | 'alert' | 'custom'

interface ActiveModal extends ModalOptions {
  kind: ModalKind
  resolve: (value: boolean) => void
}

interface FeedbackContextValue {
  notify: {
    success: (message: string, options?: Omit<NotificationOptions, 'message'>) => void
    info: (message: string, options?: Omit<NotificationOptions, 'message'>) => void
    warning: (message: string, options?: Omit<NotificationOptions, 'message'>) => void
    error: (message: string, options?: Omit<NotificationOptions, 'message'>) => void
    dismiss: (id: number) => void
    clear: () => void
  }
  modal: {
    confirm: (options: ModalOptions) => Promise<boolean>
    alert: (options: ModalOptions) => Promise<void>
    open: (options: ModalOptions) => Promise<boolean>
  }
}

const FeedbackContext = createContext<FeedbackContextValue | null>(null)

const notificationIcons = {
  success: CheckCircle2,
  info: Info,
  warning: TriangleAlert,
  error: XCircle,
}

function ToastItem({
  item,
  onDismiss,
}: {
  item: NotificationItem
  onDismiss: (id: number) => void
}) {
  const Icon = notificationIcons[item.type]

  useEffect(() => {
    if (item.duration === 0) return

    const timer = window.setTimeout(
      () => onDismiss(item.id),
      item.duration ?? 4500,
    )

    return () => window.clearTimeout(timer)
  }, [item.id, item.duration, onDismiss])

  return (
    <div
      className={`entropy-toast entropy-toast-${item.type}`}
      role={item.type === 'error' ? 'alert' : 'status'}
      aria-live={item.type === 'error' ? 'assertive' : 'polite'}
    >
      <Icon className="entropy-toast-icon" size={21} aria-hidden="true" />

      <div className="entropy-toast-body">
        {item.title && (
          <strong className="entropy-toast-title">{item.title}</strong>
        )}
        <p>{item.message}</p>
      </div>

      <button
        type="button"
        className="entropy-toast-close"
        onClick={() => onDismiss(item.id)}
        aria-label="Dismiss notification"
      >
        <X size={16} />
      </button>
    </div>
  )
}

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [activeModal, setActiveModal] = useState<ActiveModal | null>(null)
  const nextId = useRef(0)
  const modalRef = useRef<HTMLDivElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)
  const titleId = useId()
  const messageId = useId()

  const dismissNotification = useCallback((id: number) => {
    setNotifications((current) => current.filter((item) => item.id !== id))
  }, [])

  const clearNotifications = useCallback(() => {
    setNotifications([])
  }, [])

  const showNotification = useCallback(
    (
      type: NotificationType,
      message: string,
      options?: Omit<NotificationOptions, 'message'>,
    ) => {
      const id = ++nextId.current

      setNotifications((current) => [
        ...current.slice(-4),
        {
          id,
          type,
          message,
          ...options,
        },
      ])
    },
    [],
  )

  const closeModal = useCallback(
    (result: boolean) => {
      if (!activeModal) return

      activeModal.resolve(result)
      setActiveModal(null)

      window.requestAnimationFrame(() => {
        previousFocusRef.current?.focus()
        previousFocusRef.current = null
      })
    },
    [activeModal],
  )

  const openModal = useCallback(
    (kind: ModalKind, options: ModalOptions): Promise<boolean> => {
      // Resolve an existing dialog before opening another one.
      setActiveModal((current) => {
        current?.resolve(false)
        return null
      })

      previousFocusRef.current =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null

      return new Promise<boolean>((resolve) => {
        setActiveModal({
          ...options,
          kind,
          resolve,
        })
      })
    },
    [],
  )

  const confirm = useCallback(
    (options: ModalOptions) => openModal('confirm', options),
    [openModal],
  )

  const alert = useCallback(
    async (options: ModalOptions) => {
      await openModal('alert', options)
    },
    [openModal],
  )

  const open = useCallback(
    (options: ModalOptions) => openModal('custom', options),
    [openModal],
  )

  useEffect(() => {
    if (!activeModal) return

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const frame = window.requestAnimationFrame(() => {
      modalRef.current
        ?.querySelector<HTMLElement>(
          '[data-modal-primary], [data-modal-secondary]',
        )
        ?.focus()
    })

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && activeModal.dismissible !== false) {
        event.preventDefault()
        closeModal(false)
      }

      if (event.key !== 'Tab' || !modalRef.current) return

      const focusable = Array.from(
        modalRef.current.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])',
        ),
      )

      if (!focusable.length) {
        event.preventDefault()
        return
      }

      const first = focusable[0]
      const last = focusable[focusable.length - 1]

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)

    return () => {
      window.cancelAnimationFrame(frame)
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [activeModal, closeModal])

  const value: FeedbackContextValue = {
    notify: {
      success: (message, options) =>
        showNotification('success', message, options),
      info: (message, options) =>
        showNotification('info', message, options),
      warning: (message, options) =>
        showNotification('warning', message, options),
      error: (message, options) =>
        showNotification('error', message, options),
      dismiss: dismissNotification,
      clear: clearNotifications,
    },
    modal: {
      confirm,
      alert,
      open,
    },
  }

  const ModalIcon =
    activeModal?.kind === 'confirm'
      ? TriangleAlert
      : activeModal?.kind === 'alert'
        ? CheckCircle2
        : Info

  return (
    <FeedbackContext.Provider value={value}>
      {children}

      <div className="entropy-toast-container" aria-label="Notifications">
        {notifications.map((item) => (
          <ToastItem
            key={item.id}
            item={item}
            onDismiss={dismissNotification}
          />
        ))}
      </div>

      {activeModal && (
        <div
          className="entropy-modal-backdrop"
          onMouseDown={(event) => {
            if (
              event.target === event.currentTarget &&
              activeModal.dismissible !== false
            ) {
              closeModal(false)
            }
          }}
        >
          <div
            ref={modalRef}
            className="entropy-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={activeModal.message ? messageId : undefined}
          >
            <div className="entropy-modal-heading">
              <div className="entropy-modal-icon">
                <ModalIcon size={22} aria-hidden="true" />
              </div>

              <button
                type="button"
                className="entropy-modal-close"
                onClick={() => closeModal(false)}
                aria-label="Close dialog"
                disabled={activeModal.dismissible === false}
              >
                <X size={18} />
              </button>
            </div>

            <h2 id={titleId}>{activeModal.title}</h2>

            {activeModal.message && (
              <p id={messageId} className="entropy-modal-message">
                {activeModal.message}
              </p>
            )}

            {activeModal.content && (
              <div className="entropy-modal-content">
                {activeModal.content}
              </div>
            )}

            <div className="entropy-modal-actions">
              {activeModal.kind === 'confirm' && (
                <button
                  type="button"
                  className="entropy-button-secondary"
                  data-modal-secondary
                  onClick={() => closeModal(false)}
                >
                  {activeModal.cancelText ?? 'Cancel'}
                </button>
              )}

              <button
                type="button"
                className={`entropy-button-primary${
                  activeModal.destructive ? ' is-destructive' : ''
                }`}
                data-modal-primary
                onClick={() => closeModal(true)}
              >
                {activeModal.confirmText ??
                  (activeModal.kind === 'confirm' ? 'Yes' : 'OK')}
              </button>
            </div>
          </div>
        </div>
      )}
    </FeedbackContext.Provider>
  )
}

export function useFeedback(): FeedbackContextValue {
  const context = useContext(FeedbackContext)

  if (!context) {
    throw new Error(
      'useFeedback must be used within a FeedbackProvider.',
    )
  }

  return context
}
