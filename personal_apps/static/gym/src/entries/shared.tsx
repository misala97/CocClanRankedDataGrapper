import { SharedConfirmPage } from '../shared/SharedConfirmPage'
import type { SharedConfirmPayload } from '../shared/types'
import { mount } from '../mount'

mount<SharedConfirmPayload>((payload) => <SharedConfirmPage payload={payload} />)
