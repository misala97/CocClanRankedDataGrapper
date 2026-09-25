import { StartPage } from '../start/StartPage'
import type { HeutePayload } from '../start/types'
import { mount } from '../mount'

mount<HeutePayload>((payload) => <StartPage payload={payload} />)
