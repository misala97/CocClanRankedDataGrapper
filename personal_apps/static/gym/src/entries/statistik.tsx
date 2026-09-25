import { StatistikPage } from '../statistik/StatistikPage'
import type { StatistikPayload } from '../statistik/types'
import { mount } from '../mount'

mount<StatistikPayload>((payload) => <StatistikPage payload={payload} />)
