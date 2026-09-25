import { FinishedPage } from '../finished/FinishedPage'
import type { FinishedPayload } from '../finished/types'
import { mount } from '../mount'

mount<FinishedPayload>((payload) => <FinishedPage payload={payload} />)
