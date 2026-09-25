import { CataloguePage } from '../catalogue/CataloguePage'
import type { CataloguePayload } from '../catalogue/types'
import { mount } from '../mount'

// The payload is embedded rather than fetched: the page's three sorts and its
// search are re-orderings of these same rows, so there is nothing to go back
// to the server for.
mount<CataloguePayload>((payload) => <CataloguePage payload={payload} />)
