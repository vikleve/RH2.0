import { Global, Module } from '@nestjs/common';
import { CsrfGuard } from './csrf.guard';

@Global()
@Module({
  providers: [CsrfGuard],
  exports: [CsrfGuard],
})
export class CsrfModule {}

