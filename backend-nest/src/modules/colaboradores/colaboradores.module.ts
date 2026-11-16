import { Module } from '@nestjs/common';
import { ColaboradoresController } from './colaboradores.controller';
import { ColaboradoresService } from './colaboradores.service';
import { ColaboradoresRepository } from './colaboradores.repository';
import { AuthModule } from '../auth/auth.module';
import { DatabaseModule } from '../../database/database.module';

@Module({
  imports: [DatabaseModule, AuthModule],
  controllers: [ColaboradoresController],
  providers: [ColaboradoresService, ColaboradoresRepository],
  exports: [ColaboradoresService, ColaboradoresRepository],
})
export class ColaboradoresModule {}
