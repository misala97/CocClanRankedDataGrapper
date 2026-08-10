import { useWorkoutUi } from '../stores'

/**
 * Reorder is a mode, so it says so and it can be left from where you are.
 * Before this bar existed the only exit was re-opening the options sheet.
 *
 * Reads the store, not the DOM. This is the state applyReorderUI existed to
 * put back after every refresh: the server has no notion of the mode, so a
 * server-rendered body always came back with it off.
 */
export function ReorderBar() {
  const unlocked = useWorkoutUi((s) => s.reorderUnlocked)
  const setReorder = useWorkoutUi((s) => s.setReorder)

  if (!unlocked) return null

  return (
    <div className="reorder-bar">
      <span className="reorder-bar__txt">
        Reihenfolge ändern — ziehen, oder mit den Pfeiltasten verschieben.
      </span>
      <button type="button" className="reorder-bar__done"
        onClick={() => setReorder(false)}>Fertig</button>
    </div>
  )
}
