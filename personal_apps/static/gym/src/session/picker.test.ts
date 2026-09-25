import { describe, expect, it } from 'vitest'
import { listed } from './__fixtures__/catalogue'
import { clusters, found, mine, movementMeta, sections, workouts, yoursFirst } from './picker'

const names = (rows: { name: string }[]) => rows.map((row) => row.name)

describe('yoursFirst', () => {
  it('puts the one you do most on top, then the rest A-Z', () => {
    const rows = [
      listed(1, 'Scottcurls (SZ-Stange)'),
      listed(2, 'Scottcurls (Maschine, Scheiben)', { rank: 3 }),
      listed(3, 'Scottcurls (Kurzhantel)'),
      listed(4, 'Scottcurls (Maschine)', { rank: 2 }),
    ]
    expect(names(yoursFirst(rows))).toEqual(['Scottcurls (Maschine)',
      'Scottcurls (Maschine, Scheiben)', 'Scottcurls (Kurzhantel)', 'Scottcurls (SZ-Stange)'])
  })
})

describe('clusters and mine', () => {
  const rows = [
    listed(1, 'Scottcurls (Maschine)', { rank: 2, common: true }),
    listed(2, 'Rudern (Kabel)'),
    listed(3, 'Rudern (Maschine)', { rank: 1, common: true }),
    listed(4, 'Scottcurls (Maschine, Scheiben)', { rank: 3, common: true }),
    listed(5, 'Rudern (T-Bar, liegend)', { rank: 5 }),
    listed(6, 'Butterfly (Maschine)'),
    listed(7, 'Arnold Press (Kurzhantel)'),
  ]

  it('groups by movement, the movement you do most first, the never-done A-Z after', () => {
    expect(clusters(rows).map((c) => [c.movement, names(c.rows)])).toEqual([
      ['Rudern', ['Rudern (Maschine)', 'Rudern (T-Bar, liegend)', 'Rudern (Kabel)']],
      ['Scottcurls', ['Scottcurls (Maschine)', 'Scottcurls (Maschine, Scheiben)']],
      ['Arnold Press', ['Arnold Press (Kurzhantel)']],
      ['Butterfly', ['Butterfly (Maschine)']],
    ])
  })

  it('leads "Deine" with the common rows only', () => {
    expect(mine(rows).map((c) => [c.movement, names(c.rows)])).toEqual([
      ['Rudern', ['Rudern (Maschine)']],
      ['Scottcurls', ['Scottcurls (Maschine)', 'Scottcurls (Maschine, Scheiben)']],
    ])
  })
})

describe('sections', () => {
  it('lists each movement once under its group, groups in the list’s order, A-Z by German rules', () => {
    const rows = [
      listed(1, 'Überzüge (Kurzhantel)', { movement_group: 'Brust' }),
      listed(2, 'Schrägbankdrücken (Langhantel)', { movement_group: 'Brust' }),
      listed(3, 'Bankdrücken (Langhantel)', { movement_group: 'Brust' }),
      listed(4, 'Bankdrücken (Kurzhantel)', { movement_group: 'Brust' }),
      // A variant working the triceps first still sits with its movement.
      listed(5, 'Bankdrücken (Langhantel, eng)', { muscle_group: 'Trizeps', movement_group: 'Brust' }),
      listed(6, 'Latzug (Kabel)', { movement_group: 'Rücken' }),
      listed(7, 'Handgelenkcurls (Langhantel)', { movement_group: 'Unterarme' }),
    ]
    const result = sections(rows, ['Brust', 'Rücken', 'Trizeps'])
    expect(result.map((s) => [s.group, s.movements.map((m) => m.movement)])).toEqual([
      ['Brust', ['Bankdrücken', 'Schrägbankdrücken', 'Überzüge']],
      ['Rücken', ['Latzug']],
      ['Unterarme', ['Handgelenkcurls']],
    ])
    expect(names(result[0]!.movements[0]!.rows)).toEqual(['Bankdrücken (Kurzhantel)',
      'Bankdrücken (Langhantel)', 'Bankdrücken (Langhantel, eng)'])
  })
})

describe('found', () => {
  it('keeps the search contract and puts what you do first', () => {
    const rows = [
      listed(1, 'Bizepscurls (Langhantel)'),
      listed(2, 'Hammercurls (Kurzhantel)', { rank: 1 }),
      listed(3, 'Latzug (Kabel)'),
      listed(4, 'Bizepscurls (Kurzhantel)', { rank: 2 }),
    ]
    expect(found(rows, 'curls').clusters.map((c) => names(c.rows))).toEqual([
      ['Hammercurls (Kurzhantel)'],
      ['Bizepscurls (Kurzhantel)', 'Bizepscurls (Langhantel)'],
    ])
    expect(found(rows, 'nackenzieher').clusters).toEqual([])
  })
})

describe('movementMeta', () => {
  it('names the variants you do, with how often -- at most two', () => {
    const rows = yoursFirst([
      listed(1, 'Rudern (Maschine)', { rank: 1, workouts: 23 }),
      listed(2, 'Rudern (T-Bar, stehend)', { rank: 2, workouts: 20 }),
      listed(3, 'Rudern (T-Bar, liegend)', { rank: 5, workouts: 2 }),
      listed(4, 'Rudern (Kabel)'),
    ])
    expect(movementMeta(rows)).toBe('Maschine 23× · T-Bar, stehend 20×')
  })

  it('otherwise says what it is done on', () => {
    expect(movementMeta([listed(1, 'Floor Press (Langhantel)')])).toBe('Langhantel')
    expect(movementMeta(yoursFirst([
      listed(1, 'Bankdrücken (Langhantel)'), listed(2, 'Bankdrücken (Kurzhantel)'),
      listed(3, 'Bankdrücken (Langhantel, eng)'),
    ]))).toBe('Kurzhantel · Langhantel')
  })

  it('names the variants when every one is on the same Gerät', () => {
    expect(movementMeta(yoursFirst([
      listed(1, 'Brustpresse (Maschine)'), listed(2, 'Brustpresse (Maschine, schräg)'),
      listed(3, 'Brustpresse (Maschine, Scheiben)'),
    ]))).toBe('Maschine · Scheiben · schräg')
  })
})

it('counts workouts in words', () => {
  expect([workouts(1), workouts(12)]).toEqual(['1 Workout', '12 Workouts'])
})
