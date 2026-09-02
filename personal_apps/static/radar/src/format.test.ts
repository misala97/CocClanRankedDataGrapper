import { describe, expect, it } from 'vitest'

import { UNKNOWN, count, dayStamp, decodeEntities, divergence, exchangeLabel,
         formatMarketDate, formatPrice, formatQuoteAge, money, move, postStamp,
         rowPrice, segmentLabel, signed, sourceLabel, stampTime, zscore }
  from './format'

describe('an unknown never renders as a zero', () => {
  // The single rule PRODUCT.md is most insistent about. A row with no quote,
  // or a frozen tape, has no divergence -- and 0.00 means something else
  // entirely: that chatter and price moved together.
  it('says so in words for divergence', () => {
    expect(divergence(null)).toBe('not scored')
    expect(divergence(0)).toBe('0.00')
  })

  it('uses an em-dash for an unknown price move', () => {
    expect(move(null)).toBe('—')
    expect(move(0)).toBe('0.00%')
  })

  it('uses an em-dash for an unscored window', () => {
    expect(zscore(null)).toBe('—')
    expect(zscore(0)).toBe('0.0')
  })
})

describe('signed numbers', () => {
  it('marks a rise and sets a fall with a real minus', () => {
    // U+2212, not the hyphen: the row's move already used it and the
    // divergence column did not, so `-0.68` and `−4.5%` sat one column
    // apart in two dialects (critique, 2026-09-01).
    expect(signed(1.5, 2)).toBe('+1.50')
    expect(signed(-1.5, 2)).toBe('−1.50')
    expect(move(-0.004)).toBe('−0.40%')
  })

  it('never prints a negative zero', () => {
    // toFixed(-0.001) is "-0.00", which reads as a downward move that did not
    // happen -- and on a price column that is a wrong fact, not a typo.
    expect(signed(-0.001, 2)).toBe('0.00')
    expect(move(-0.0000001)).toBe('0.00%')
  })
})

describe('labels', () => {
  it('renders a source the label table does not know', () => {
    // Adding a source must be a config entry plus an ingest module, never a
    // UI change (PRODUCT.md). An unknown key falling through as itself is
    // what keeps that true.
    expect(sourceLabel('bluesky')).toBe('Bluesky')
    expect(sourceLabel('discord')).toBe('discord')
    expect(segmentLabel('nonsense')).toBe('nonsense')
  })

  it('names the venue, not the subreddit', () => {
    // Since 2026-08-26 a stored Reddit source name carries its subreddit, so
    // that one sub's feed rolling over marks its own buckets truncated
    // rather than every other sub's. That is a decision about how status and
    // scoring are partitioned, NOT a decision to put subreddits on the
    // surface -- and without the rooting the raw key leaked through the
    // fallback and post badges read `reddit:wallstreetbets` next to
    // `Bluesky`.
    expect(sourceLabel('reddit')).toBe('Reddit')
    expect(sourceLabel('reddit:wallstreetbets')).toBe('Reddit')
    expect(sourceLabel('reddit:pennystocks')).toBe('Reddit')
  })

  it('still falls through for an unknown root with a suffix', () => {
    expect(sourceLabel('discord:general')).toBe('discord:general')
  })
})

describe('the stamp', () => {
  it('formats the same UTC instant in Berlin summer time', () => {
    /* A date stored as UTC must be read in Radar's fixed display timezone,
       not in the browser's own timezone. */
    expect(stampTime('2026-08-28T19:04:11Z')).toBe('21:04 CEST')
  })

  it('formats Berlin winter time without using the machine timezone', () => {
    expect(stampTime('2026-01-28T19:04:11Z')).toBe('20:04 CET')
  })

  it('does not crash on a malformed timestamp', () => {
    expect(stampTime('not a date')).toBe('—')
  })

  it('dates retained posts in Berlin time', () => {
    // Posts remain visible for thirty days. A bare "19:04" cannot tell
    // yesterday from last week, and it silently relies on the reader knowing
    // that every clock on this surface is UTC.
    expect(postStamp('2026-08-22T19:04:11Z'))
      .toBe('22 Aug 2026 · 21:04 CEST')
  })

  it('dates in English, in Berlin time', () => {
    // The surface is English (PRODUCT.md). `22. Aug. 2026` was the one
    // German-formatted date on it, next to en-US counts that had been
    // de-localised on purpose.
    expect(formatMarketDate('2026-08-22T19:04:11Z')).toBe('22 Aug 2026')
    expect(formatMarketDate('2026-12-31T23:30:00Z')).toBe('1 Jan 2027')
  })
})

describe('what the source escaped', () => {
  it('is decoded as text, once', () => {
    // Reddit hands out `&amp;` inside URLs and bodies. Once, deliberately:
    // `&amp;amp;` is a source that double-escaped, and turning it into `&`
    // would be inventing a character the post never had.
    expect(decodeEntities('AT&amp;T &lt;3 &quot;x&quot; &#39;y&#39;'))
      .toBe('AT&T <3 "x" \'y\'')
    expect(decodeEntities('&amp;amp;')).toBe('&amp;')
    expect(decodeEntities('plain')).toBe('plain')
  })
})

describe('the panel identity line', () => {
  it('names the exchange rather than printing its code', () => {
    /* The panel read `Q · large cap · $2.9T`. Q is a listing code, not a
       thing a reader knows. */
    expect(exchangeLabel('Q')).toBe('Nasdaq Global Select')
    expect(exchangeLabel('S')).toBe('Nasdaq Capital Market')
    expect(exchangeLabel('P')).toBe('NYSE Arca')
  })

  it('renders a code it has never seen rather than dropping it', () => {
    expect(exchangeLabel('ZZ')).toBe('ZZ')
    expect(exchangeLabel(null)).toBeNull()
  })
})

describe('a date inside a sentence', () => {
  it('is not the storage format', () => {
    expect(dayStamp('2026-07-22')).toBe('22 Jul 2026')
  })

  it('is an unknown, not an empty string, when there is no date', () => {
    expect(dayStamp(null)).toBe(UNKNOWN)
  })
})

describe('the price under a ticker', () => {
  it('says the exchange is shut rather than showing a live-looking number', () => {
    expect(rowPrice(1.84, 'closed')).toBe('closed at $1.84')
  })

  // Was pinned the other way: null said "no quote" and 0 said "$0.00", on the
  // reading that the two are different facts. They are not. No listed share
  // prints at zero, so a zero here is an absent quote that arrived as a
  // default -- and PRODUCT.md's rule is that an empty must read as "not
  // known", never as a zero. `$0.00` is the most confident wrong number the
  // row can carry, and it is the one a penny stock is most likely to get.
  it('treats a quote of zero as no quote, not as a price of nothing', () => {
    expect(rowPrice(null, 'ok')).toBe('no quote')
    expect(rowPrice(0, 'ok')).toBe('no quote')
    expect(rowPrice(-0.01, 'ok')).toBe('no quote')
  })

  // The micro segment is what this board is FOR, and two decimals rounds its
  // entire price range to $0.00.
  it('keeps a sub-dollar price at a precision that still has a price in it', () => {
    expect(rowPrice(0.0031, 'ok')).toBe('$0.0031')
    expect(rowPrice(0.0031, 'closed')).toBe('closed at $0.0031')
  })

  it('drops the cents once they are noise', () => {
    expect(rowPrice(1.84, 'ok')).toBe('$1.84')
    expect(rowPrice(202.4, 'ok')).toBe('$202')
  })
})

describe('money', () => {
  it('formats venue currency explicitly', () => {
    /* The formatter must report the venue's real currency; Germany-mode US
       fallbacks are dollars, not synthetic euros. */
    expect(formatPrice(194.2, 'EUR')).toBe('194,20\u00a0€')
    expect(formatPrice(220.5, 'USD', { explicitCode: true }))
      .toBe('220,50\u00a0$ · USD')
  })

  it('labels delayed quote age in a human unit and preserves an unknown age', () => {
    expect(formatQuoteAge(720)).toBe('12 min delayed')
    // "2740 min stale" asked the reader to finish a subtraction; the row
    // stopped doing that on 2026-08-30 and the panel had not caught up.
    expect(formatQuoteAge(164600)).toBe('45h delayed')
    expect(formatQuoteAge(null)).toBe(UNKNOWN)
  })

  // The two axis labels either side of one chart are formatted from the same
  // scale so they cannot come out as `$202` above `$46.33`.
  it('formats both ends of a range by the larger end', () => {
    expect(money(202.4, 202.4)).toBe('$202')
    expect(money(46.33, 202.4)).toBe('$46')
    expect(money(0.0031, 0.0104)).toBe('$0.0031')
  })
})

describe('count', () => {
  it('groups a figure too long to read at a glance', () => {
    expect(count(1284392)).toBe('1,284,392')
  })

  // Pinned to en-US for the same reason the clock is pinned to UTC: one
  // number in `1.284.392` under a German locale would be the only figure on
  // the surface in a different convention.
  it('does not follow the reader locale', () => {
    expect(count(1000)).toBe('1,000')
  })
})

describe('money in the venue currency', () => {
  it('prints the euro sign for a German quote and keeps the dollar default', () => {
    expect(money(1.5, 1.5, 'EUR')).toBe('€1.50')
    expect(money(202.4, 202.4, 'EUR')).toBe('€202')
    expect(money(1.5, 1.5)).toBe('$1.50')
    expect(money(1.5, 1.5, 'GBP')).toBe('GBP 1.50')
  })
})
