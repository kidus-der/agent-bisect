import { Check, Copy, X } from 'lucide-react'

import { InstrumentLabel } from '@/components/primitives/InstrumentLabel'
import { Panel } from '@/components/primitives/Panel'
import { type CopyStatus, useCopy } from '@/lib/useCopy'
import { cn } from '@/lib/utils'

import { checkBadge } from './checkRef'

import { type CommentBlock, type Span, parseCommentMarkdown } from './commentMarkdown'

const COPY_LABELS: Readonly<Record<CopyStatus, string>> = {
  idle: 'Copy markdown',
  copied: 'Copied',
  failed: 'Copy failed',
}

/** Labelled rather than icon-only: this is the action the page exists to offer. */
function CopyMarkdownButton({ markdown }: { readonly markdown: string }) {
  const { status, copy } = useCopy()
  const Icon = status === 'copied' ? Check : status === 'failed' ? X : Copy
  return (
    <button
      type="button"
      onClick={() => void copy(markdown)}
      className={cn(
        'inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-control border px-2.5 text-small font-medium',
        status === 'failed'
          ? 'border-fail/40 bg-fail-tint text-fail'
          : 'border-line-strong bg-elevated text-ink hover:border-ink-muted',
      )}
    >
      <Icon aria-hidden="true" className="size-3.5" />
      {COPY_LABELS[status]}
    </button>
  )
}

function Spans({ spans }: { readonly spans: readonly Span[] }) {
  return (
    <>
      {spans.map((span, index) => {
        const key = `${span.kind}-${index}-${span.text}`
        if (span.kind === 'strong') {
          return (
            <strong key={key} className="font-semibold text-ink">
              {span.text}
            </strong>
          )
        }
        if (span.kind === 'code') {
          return (
            <code
              key={key}
              className="rounded-step border border-line bg-ground px-1 py-0.5 num text-[12px] text-ink"
            >
              {span.text}
            </code>
          )
        }
        return <span key={key}>{span.text}</span>
      })}
    </>
  )
}

function Block({ block }: { readonly block: CommentBlock }) {
  if (block.kind === 'heading') {
    return (
      <p
        className={cn(
          'font-semibold text-ink',
          block.level === 1 ? 'text-h2' : block.level === 2 ? 'text-h3' : 'text-body',
        )}
      >
        <Spans spans={block.spans} />
      </p>
    )
  }
  if (block.kind === 'definition') {
    return (
      <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-[minmax(0,11rem)_minmax(0,1fr)]">
        <span className="pt-0.5 label-instrument">{block.term}</span>
        <span className="num text-small text-ink">
          <Spans spans={block.spans} />
        </span>
      </div>
    )
  }
  if (block.kind === 'diff') {
    const added = block.sign === '+'
    return (
      <p
        className={cn(
          'rounded-step border-l-2 py-0.5 pl-2 num text-small',
          added ? 'border-pass bg-pass-tint text-ink' : 'border-fail bg-fail-tint text-ink',
        )}
      >
        <span aria-hidden="true" className={added ? 'text-pass' : 'text-fail'}>
          {block.sign}{' '}
        </span>
        <span className="sr-only">{added ? 'added: ' : 'removed: '}</span>
        {block.text}
      </p>
    )
  }
  if (block.kind === 'bullet') {
    return (
      <p className="flex gap-2 text-small text-ink">
        <span aria-hidden="true" className="text-ink-muted">
          •
        </span>
        <span>
          <Spans spans={block.spans} />
        </span>
      </p>
    )
  }
  return (
    <p className="text-small text-pretty text-ink-muted">
      <Spans spans={block.spans} />
    </p>
  )
}

interface CommentPreviewProps {
  readonly markdown: string
  /** Absent when the gate compared two refs rather than a pull request. */
  readonly prNumber: number | null
}

/**
 * The comment the GitHub Action actually posts, shown as it will appear.
 *
 * Rendered from the parsed block tree as React elements — there is no
 * `dangerouslySetInnerHTML` here and no HTML string anywhere in the path, so
 * markup in the body renders inert as literal text.
 */
export function CommentPreview({ markdown, prNumber }: CommentPreviewProps) {
  const blocks = parseCommentMarkdown(markdown)
  return (
    <Panel variant="card" bodyClassName="flex flex-col gap-3">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <InstrumentLabel>pr_comment</InstrumentLabel>
        <CopyMarkdownButton markdown={markdown} />
      </header>

      {/* GitHub comment chrome: avatar gutter, then a bordered body with a header strip. */}
      <div className="flex gap-3">
        <span
          aria-hidden="true"
          className="mt-1 hidden size-8 shrink-0 items-center justify-center rounded-pill border border-line-strong bg-elevated text-small font-semibold text-ink sm:flex"
        >
          B
        </span>
        <div className="relative min-w-0 flex-1 rounded-card border border-line-strong bg-surface">
          <span
            aria-hidden="true"
            className="absolute top-3.5 -left-[7px] hidden size-3 rotate-45 border-b border-l border-line-strong bg-elevated sm:block"
          />
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-t-card border-b border-line-strong bg-elevated px-4 py-2">
            <span className="num text-small font-semibold text-ink">bisect-bot</span>
            <span className="text-small text-ink-muted">
              {prNumber === null ? 'would comment' : 'commented on'}
            </span>
            {prNumber === null ? null : (
              <span className="num text-small text-ink-muted">{checkBadge(prNumber)}</span>
            )}
            <span className="ml-auto rounded-pill border border-line px-1.5 py-0.5 label-instrument">
              bot
            </span>
          </div>
          <div className="flex flex-col gap-2 px-4 py-4">
            {blocks.map((block, index) => (
              <Block key={`${block.kind}-${index}`} block={block} />
            ))}
          </div>
        </div>
      </div>
    </Panel>
  )
}
